"""On-Behalf-Of: troca o token do usuário (aud = este MCP) por um token de API downstream."""

import hashlib
import logging
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any, Protocol

import anyio
import msal

from utg_mcp.core.cache import KeyedLocks, TtlCache
from utg_mcp.core.errors import (
    AppError,
    AuthenticationRequired,
    ConfigurationError,
    UpstreamUnavailable,
)

logger = logging.getLogger(__name__)

_REAUTH_ERRORS = frozenset(
    {"invalid_grant", "interaction_required", "consent_required", "login_required"}
)
_CONFIG_ERRORS = frozenset(
    {"invalid_client", "unauthorized_client", "invalid_scope", "invalid_request"}
)


class OboClient(Protocol):
    def acquire_token_on_behalf_of(
        self, user_assertion: str, scopes: list[str]
    ) -> dict[str, Any]: ...


class _DiscardingTokenCache(msal.TokenCache):  # type: ignore[misc]
    """Cache do MSAL que não armazena nada.

    `acquire_token_on_behalf_of` nunca consulta o cache do MSAL, mas grava nele cada resposta
    (AT/RT/ID token) — sem isto a memória do processo cresce indefinidamente. O cache efetivo
    dos tokens OBO é o `TtlCache` (limitado) de `OboTokenProvider`.
    """

    def add(self, event: dict[str, Any], now: float | None = None) -> None:
        return


class OboTokenProvider:
    _EXPIRY_MARGIN_SECONDS = 300
    _MIN_TTL_SECONDS = 60

    def __init__(
        self,
        *,
        client_factory: Callable[[], OboClient],
        max_entries: int = 5000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client_factory = client_factory
        self._client: OboClient | None = None
        self._client_lock = threading.Lock()
        self._cache: TtlCache[str, str] = TtlCache(max_entries=max_entries, clock=clock)
        self._locks = KeyedLocks()

    @classmethod
    def for_entra(cls, *, tenant_id: str, client_id: str, client_secret: str) -> "OboTokenProvider":
        def factory() -> OboClient:
            app: OboClient = msal.ConfidentialClientApplication(
                client_id=client_id,
                client_credential=client_secret,
                authority=f"https://login.microsoftonline.com/{tenant_id}",
                token_cache=_DiscardingTokenCache(),
            )
            return app

        return cls(client_factory=factory)

    async def get_token(self, assertion: str, scopes: Sequence[str]) -> str:
        key = hashlib.sha256(f"{' '.join(sorted(scopes))}|{assertion}".encode()).hexdigest()
        if (cached := self._cache.get(key)) is not None:
            return cached

        async with self._locks.hold(key):
            if (cached := self._cache.get(key)) is not None:
                return cached
            try:
                result = await anyio.to_thread.run_sync(self._acquire, assertion, list(scopes))
            except AppError:
                raise
            except Exception as exc:
                logger.exception("obo_client_failure")
                raise UpstreamUnavailable("obo_client_failure") from exc

            access_token = result.get("access_token")
            if not access_token:
                raise _map_error(result)

            expires_in = int(result.get("expires_in", 3600))
            ttl = max(expires_in - self._EXPIRY_MARGIN_SECONDS, self._MIN_TTL_SECONDS)
            self._cache.set(key, str(access_token), ttl)
            return str(access_token)

    def _acquire(self, assertion: str, scopes: list[str]) -> dict[str, Any]:
        with self._client_lock:
            if self._client is None:
                self._client = self._client_factory()
            client = self._client
        return client.acquire_token_on_behalf_of(user_assertion=assertion, scopes=scopes)


def _map_error(result: dict[str, Any]) -> AppError:
    error = str(result.get("error", "unknown"))
    # error_description pode ecoar UPN/detalhes — loga apenas códigos e correlation id.
    logger.warning(
        "obo_failed",
        extra={
            "error": error,
            "error_codes": result.get("error_codes"),
            "correlation_id": result.get("correlation_id"),
        },
    )
    if error in _REAUTH_ERRORS:
        return AuthenticationRequired(f"obo:{error}")
    if error in _CONFIG_ERRORS:
        return ConfigurationError(f"obo:{error}")
    return UpstreamUnavailable(f"obo:{error}")
