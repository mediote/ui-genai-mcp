"""Validação de access tokens do Entra ID emitidos para este servidor MCP (resource server).

Aceita apenas tokens delegados (de usuário) com `scp`, emitidos para o app registration
configurado (v1 ou v2). Nunca aceita tokens de outros recursos (sem token passthrough).
"""

import logging
from typing import Any, Protocol

import anyio
import jwt
from mcp.server.auth.provider import AccessToken, TokenVerifier

logger = logging.getLogger(__name__)

_ALGORITHM = "RS256"
_CLAIMS_KEPT = (
    "oid",
    "tid",
    "name",
    "preferred_username",
    "upn",
    "azp",
    "appid",
    "ver",
    "aud",
    "iss",
    "idtyp",
)


class SigningKeyResolver(Protocol):
    # A chave é um objeto de chave pública do `cryptography` (tipo varia por algoritmo).
    async def resolve(self, token: str) -> Any: ...  # noqa: ANN401


class JwksSigningKeyResolver:
    """Resolve a chave pública pelo `kid` usando o JWKS do tenant (com cache do PyJWT)."""

    def __init__(self, jwks_url: str) -> None:
        self._client = jwt.PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=3600, timeout=5)

    async def resolve(self, token: str) -> Any:  # noqa: ANN401
        # Pode fazer I/O bloqueante (download do JWKS) — executa fora do event loop.
        signing_key = await anyio.to_thread.run_sync(self._client.get_signing_key_from_jwt, token)
        return signing_key.key


class EntraTokenVerifier(TokenVerifier):
    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        key_resolver: SigningKeyResolver,
        leeway_seconds: int = 60,
    ) -> None:
        self._tenant_id = tenant_id
        self._api_audience = f"api://{client_id}"
        self._audiences = [client_id, self._api_audience]
        self._issuers = [
            f"https://login.microsoftonline.com/{tenant_id}/v2.0",
            f"https://sts.windows.net/{tenant_id}/",
        ]
        self._keys = key_resolver
        self._leeway = leeway_seconds

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            if jwt.get_unverified_header(token).get("alg") != _ALGORITHM:
                return _reject("unsupported_alg")
            key = await self._keys.resolve(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=[_ALGORITHM],
                audience=self._audiences,
                issuer=self._issuers,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError:
            return _reject("expired")
        except jwt.InvalidAudienceError:
            return _reject("audience")
        except jwt.InvalidIssuerError:
            return _reject("issuer")
        except jwt.PyJWTError as exc:
            return _reject(f"invalid_token:{type(exc).__name__}")
        except Exception:
            logger.exception("token_verification_error")
            return None

        if claims.get("tid") != self._tenant_id:
            return _reject("tenant")

        scp = claims.get("scp")
        oid = claims.get("oid")
        if not isinstance(scp, str) or not scp.strip() or not oid or claims.get("idtyp") == "app":
            # Token app-only (managed identity / agent identity) — sinal-chave do spike da Fase 0.
            return _reject("not_user_token")

        return AccessToken(
            token=token,
            client_id=str(claims.get("azp") or claims.get("appid") or "unknown"),
            # O SDK compara scopes literalmente com AuthSettings.required_scopes (URIs completas).
            scopes=[f"{self._api_audience}/{scope}" for scope in scp.split()],
            expires_at=int(claims["exp"]),
            subject=str(oid),
            claims={name: claims[name] for name in _CLAIMS_KEPT if name in claims},
        )


def _reject(reason: str) -> AccessToken | None:
    logger.warning("access_token_rejected", extra={"reason": reason})
    return None
