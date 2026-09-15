import msal
import pytest

from utg_mcp.auth import obo

GRAPH_SCOPES = ["https://graph.microsoft.com/.default"]
TOKEN_EVENT = {
    "client_id": "client",
    "scope": GRAPH_SCOPES,
    "token_endpoint": "https://login.microsoftonline.com/tenant/oauth2/v2.0/token",
    "response": {"access_token": "at", "expires_in": 3600, "token_type": "Bearer"},
}
ACCESS_TOKEN = msal.TokenCache.CredentialType.ACCESS_TOKEN


def test_msal_default_cache_would_store_obo_tokens():
    cache = msal.TokenCache()
    cache.add(dict(TOKEN_EVENT))

    assert list(cache.search(ACCESS_TOKEN)) != []


def test_discarding_cache_never_stores_tokens():
    cache = obo._DiscardingTokenCache()
    cache.add(dict(TOKEN_EVENT))

    assert list(cache.search(ACCESS_TOKEN)) == []


@pytest.mark.anyio
async def test_for_entra_wires_discarding_cache(monkeypatch):
    captured: dict[str, object] = {}

    class FakeConfidentialClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def acquire_token_on_behalf_of(self, user_assertion, scopes):
            return {"access_token": "graph-token", "expires_in": 3600}

    monkeypatch.setattr(obo.msal, "ConfidentialClientApplication", FakeConfidentialClient)
    provider = obo.OboTokenProvider.for_entra(tenant_id="tenant", client_id="c", client_secret="s")

    token = await provider.get_token("assertion", GRAPH_SCOPES)

    assert token == "graph-token"
    assert isinstance(captured["token_cache"], obo._DiscardingTokenCache)
    assert captured["authority"] == "https://login.microsoftonline.com/tenant"
