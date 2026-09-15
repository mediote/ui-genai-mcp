"""Cliente assíncrono do Microsoft Graph com identidade delegada do usuário (via OBO)."""

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Protocol

import anyio
import httpx

from utg_mcp.auth.current_user import CurrentUser
from utg_mcp.core.errors import (
    AuthenticationRequired,
    ConfigurationError,
    PermissionDenied,
    ResourceNotFound,
    UpstreamUnavailable,
)

logger = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_DEFAULT_SCOPES = ("https://graph.microsoft.com/.default",)
_RETRYABLE_STATUS = frozenset({429, 503, 504})
_MAX_RETRY_AFTER_SECONDS = 5.0


class DelegatedTokenProvider(Protocol):
    async def get_token(self, assertion: str, scopes: Sequence[str]) -> str: ...


class GraphClient:
    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        token_provider: DelegatedTokenProvider,
        base_url: str = GRAPH_BASE_URL,
        max_retries: int = 2,
        sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
    ) -> None:
        self._http = http
        self._tokens = token_provider
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._sleep = sleep

    async def get_json(
        self, user: CurrentUser, path: str, *, params: Mapping[str, str] | None = None
    ) -> dict[str, Any]:
        response = await self._get(user, path, params)
        try:
            data = response.json()
        except ValueError as exc:
            raise UpstreamUnavailable("graph_invalid_json") from exc
        if not isinstance(data, dict):
            raise UpstreamUnavailable("graph_unexpected_payload")
        return data

    async def _get(
        self, user: CurrentUser, path: str, params: Mapping[str, str] | None
    ) -> httpx.Response:
        if not user.assertion:
            raise AuthenticationRequired("graph_call_without_user_assertion")
        token = await self._tokens.get_token(user.assertion, GRAPH_DEFAULT_SCOPES)
        url = f"{self._base_url}/{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {token}"}

        for attempt in range(self._max_retries + 1):
            is_last = attempt == self._max_retries
            try:
                response = await self._http.get(url, params=params, headers=headers)
            except httpx.TimeoutException as exc:
                if is_last:
                    raise UpstreamUnavailable("graph_timeout") from exc
                continue
            except httpx.HTTPError as exc:
                raise UpstreamUnavailable(f"graph_transport_error:{type(exc).__name__}") from exc

            if response.status_code in _RETRYABLE_STATUS and not is_last:
                await self._sleep(_retry_after_seconds(response))
                continue
            return _raise_for_status(response)

        raise UpstreamUnavailable("graph_retries_exhausted")  # pragma: no cover


def _retry_after_seconds(response: httpx.Response) -> float:
    try:
        value = float(response.headers.get("retry-after", "1"))
    except ValueError:
        value = 1.0
    return min(max(value, 0.0), _MAX_RETRY_AFTER_SECONDS)


def _raise_for_status(response: httpx.Response) -> httpx.Response:
    status = response.status_code
    if status < 400:
        return response
    logger.warning(
        "graph_error_response",
        extra={"status": status, "graph_request_id": response.headers.get("request-id")},
    )
    if status == 401:
        raise AuthenticationRequired("graph_401")
    if status == 403:
        raise PermissionDenied("graph_403")
    if status == 404:
        raise ResourceNotFound("graph_404")
    if status in _RETRYABLE_STATUS or status >= 500:
        raise UpstreamUnavailable(f"graph_{status}")
    raise ConfigurationError(f"graph_{status}")
