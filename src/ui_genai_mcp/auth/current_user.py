"""Identidade do usuário autenticado na chamada MCP corrente."""

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field

from mcp.server.auth.middleware.auth_context import get_access_token

from ui_genai_mcp.core.errors import AuthenticationRequired


@dataclass(frozen=True, slots=True)
class CurrentUser:
    oid: str
    tenant_id: str
    name: str
    upn: str
    client_app_id: str
    scopes: tuple[str, ...]
    token_version: str
    audience: str
    # Token bruto do usuário — usado APENAS como assertion no OBO. Nunca logar/repassar.
    assertion: str | None = field(default=None, repr=False)

    @property
    def user_ref(self) -> str:
        """Identificador pseudonimizado para logs (LGPD)."""
        return hashlib.sha256(f"{self.tenant_id}:{self.oid}".encode()).hexdigest()[:16]

    def has_scopes(self, required: Iterable[str]) -> bool:
        return set(required) <= set(self.scopes)


DEV_USER = CurrentUser(
    oid="dev-user",
    tenant_id="dev",
    name="Dev User",
    upn="dev@localhost",
    client_app_id="dev",
    scopes=(),
    token_version="dev",  # noqa: S106 — rótulo do modo dev, não é segredo
    audience="dev",
)


def resolve_current_user(*, auth_enabled: bool) -> CurrentUser:
    token = get_access_token()
    if token is None:
        if not auth_enabled:
            return DEV_USER
        raise AuthenticationRequired("no access token in request context")

    claims = token.claims or {}
    return CurrentUser(
        oid=token.subject or "",
        tenant_id=str(claims.get("tid", "")),
        name=str(claims.get("name", "")),
        upn=str(claims.get("preferred_username") or claims.get("upn") or ""),
        client_app_id=token.client_id,
        scopes=tuple(token.scopes),
        token_version=str(claims.get("ver", "")),
        audience=str(claims.get("aud", "")),
        assertion=token.token,
    )
