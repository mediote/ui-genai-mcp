"""Constantes e dublês compartilhados pelos testes."""

import time
from collections.abc import Sequence
from typing import Any

import jwt

TENANT_ID = "11111111-1111-1111-1111-111111111111"
CLIENT_ID = "22222222-2222-2222-2222-222222222222"
USER_OID = "33333333-3333-3333-3333-333333333333"
CALLER_APP_ID = "44444444-4444-4444-4444-444444444444"
PUBLIC_BASE_URL = "https://mcp.test"
REQUIRED_SCOPE_URI = f"api://{CLIENT_ID}/access_as_user"


class StaticKeyResolver:
    def __init__(self, key: Any) -> None:
        self.key = key
        self.calls = 0

    async def resolve(self, token: str) -> Any:
        self.calls += 1
        return self.key


class FailingKeyResolver:
    async def resolve(self, token: str) -> Any:
        raise RuntimeError("jwks unavailable")


class FakeTokenProvider:
    def __init__(self, token: str = "graph-token") -> None:
        self.token = token
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    async def get_token(self, assertion: str, scopes: Sequence[str]) -> str:
        self.calls.append((assertion, tuple(scopes)))
        return self.token


def build_claims(*, version: str = "v2", **overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    if version == "v2":
        claims: dict[str, Any] = {
            "aud": CLIENT_ID,
            "iss": f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
            "azp": CALLER_APP_ID,
            "preferred_username": "ana.teste@example.com",
            "ver": "2.0",
        }
    else:
        claims = {
            "aud": f"api://{CLIENT_ID}",
            "iss": f"https://sts.windows.net/{TENANT_ID}/",
            "appid": CALLER_APP_ID,
            "upn": "ana.teste@example.com",
            "ver": "1.0",
        }
    claims.update(
        {
            "iat": now,
            "nbf": now,
            "exp": now + 3600,
            "tid": TENANT_ID,
            "oid": USER_OID,
            "name": "Ana Teste",
            "scp": "access_as_user",
        }
    )
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def sign(claims: dict[str, Any], private_key: Any, *, algorithm: str = "RS256") -> str:
    return jwt.encode(claims, private_key, algorithm=algorithm, headers={"kid": "test-kid"})
