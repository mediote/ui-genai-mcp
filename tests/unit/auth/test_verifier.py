import logging

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from support import (
    CALLER_APP_ID,
    CLIENT_ID,
    REQUIRED_SCOPE_URI,
    TENANT_ID,
    USER_OID,
    FailingKeyResolver,
    StaticKeyResolver,
    build_claims,
    sign,
)
from ui_genai_mcp.auth.verifier import EntraTokenVerifier

pytestmark = pytest.mark.anyio


def _verifier(resolver: object) -> EntraTokenVerifier:
    return EntraTokenVerifier(tenant_id=TENANT_ID, client_id=CLIENT_ID, key_resolver=resolver)  # type: ignore[arg-type]


async def test_accepts_v2_user_token_and_maps_claims(key_resolver, make_token):
    token = make_token()

    access = await _verifier(key_resolver).verify_token(token)

    assert access is not None
    assert access.token == token
    assert access.subject == USER_OID
    assert access.client_id == CALLER_APP_ID
    assert access.scopes == [REQUIRED_SCOPE_URI]
    assert access.claims is not None
    assert access.claims["preferred_username"] == "ana.teste@example.com"
    assert "scp" not in access.claims


async def test_accepts_v1_token_with_api_audience(key_resolver, make_token):
    access = await _verifier(key_resolver).verify_token(make_token(version="v1"))

    assert access is not None
    assert access.client_id == CALLER_APP_ID
    assert access.claims is not None
    assert access.claims["ver"] == "1.0"


async def test_maps_multiple_scopes_to_full_uris(key_resolver, make_token):
    access = await _verifier(key_resolver).verify_token(make_token(scp="access_as_user Org.Read"))

    assert access is not None
    assert access.scopes == [REQUIRED_SCOPE_URI, f"api://{CLIENT_ID}/Org.Read"]


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"exp": 1}, id="expired"),
        pytest.param({"aud": "api://outro-app"}, id="wrong-audience"),
        pytest.param({"aud": "https://graph.microsoft.com"}, id="graph-audience"),
        pytest.param({"iss": "https://login.microsoftonline.com/outro/v2.0"}, id="wrong-issuer"),
        pytest.param({"tid": "outro-tenant"}, id="wrong-tenant"),
        pytest.param({"scp": None, "roles": ["App.Read"], "idtyp": "app"}, id="app-only"),
        pytest.param({"scp": "   "}, id="blank-scope"),
        pytest.param({"oid": None}, id="missing-oid"),
    ],
)
async def test_rejects_invalid_claims(key_resolver, rsa_private_key, overrides):
    token = sign(build_claims(**overrides), rsa_private_key)

    assert await _verifier(key_resolver).verify_token(token) is None


async def test_rejects_token_signed_by_another_key(key_resolver):
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = sign(build_claims(), other_key)

    assert await _verifier(key_resolver).verify_token(token) is None


async def test_rejects_symmetric_algorithm_without_resolving_key():
    resolver = StaticKeyResolver("irrelevant")
    token = jwt.encode(build_claims(), "a-shared-secret-with-enough-length!!", algorithm="HS256")

    assert await _verifier(resolver).verify_token(token) is None
    assert resolver.calls == 0


async def test_rejects_garbage_token(key_resolver):
    assert await _verifier(key_resolver).verify_token("not-a-jwt") is None


async def test_key_resolution_failure_returns_none(make_token):
    assert await _verifier(FailingKeyResolver()).verify_token(make_token()) is None


async def test_never_logs_raw_token(key_resolver, make_token, caplog):
    caplog.set_level(logging.DEBUG)
    token = make_token(exp=1)

    await _verifier(key_resolver).verify_token(token)

    assert token not in caplog.text
    assert any(getattr(r, "reason", None) == "expired" for r in caplog.records)
