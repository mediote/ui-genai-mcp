from dataclasses import replace

import httpx
import pytest

from support import FakeTokenProvider
from ui_genai_mcp.auth.current_user import CurrentUser
from ui_genai_mcp.core.errors import (
    AuthenticationRequired,
    ConfigurationError,
    PermissionDenied,
    ResourceNotFound,
    UpstreamUnavailable,
)
from ui_genai_mcp.integrations.graph import GRAPH_DEFAULT_SCOPES, GraphClient

pytestmark = pytest.mark.anyio

USER = CurrentUser(
    oid="oid",
    tenant_id="tid",
    name="Ana",
    upn="ana@example.com",
    client_app_id="app",
    scopes=(),
    token_version="2.0",
    audience="aud",
    assertion="user-assertion",
)


def _client(handler, sleeps: list[float] | None = None) -> tuple[GraphClient, FakeTokenProvider]:
    provider = FakeTokenProvider()

    async def fake_sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GraphClient(http=http, token_provider=provider, sleep=fake_sleep), provider


async def test_get_json_uses_obo_token_not_user_assertion():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"displayName": "Ana"})

    graph, provider = _client(handler)

    data = await graph.get_json(USER, "/me", params={"$select": "displayName"})

    assert data == {"displayName": "Ana"}
    assert provider.calls == [("user-assertion", GRAPH_DEFAULT_SCOPES)]
    assert seen[0].headers["authorization"] == "Bearer graph-token"
    assert str(seen[0].url) == "https://graph.microsoft.com/v1.0/me?%24select=displayName"


async def test_requires_user_assertion():
    graph, _ = _client(lambda r: httpx.Response(200, json={}))

    with pytest.raises(AuthenticationRequired):
        await graph.get_json(replace(USER, assertion=None), "me")


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, AuthenticationRequired),
        (403, PermissionDenied),
        (404, ResourceNotFound),
        (400, ConfigurationError),
        (500, UpstreamUnavailable),
    ],
)
async def test_maps_error_status(status, expected):
    graph, _ = _client(lambda r: httpx.Response(status, json={"error": {}}))

    with pytest.raises(expected):
        await graph.get_json(USER, "me")


async def test_retries_throttling_honoring_retry_after():
    responses = iter(
        [httpx.Response(429, headers={"Retry-After": "2"}), httpx.Response(200, json={"ok": True})]
    )
    sleeps: list[float] = []
    graph, _ = _client(lambda r: next(responses), sleeps)

    assert await graph.get_json(USER, "me") == {"ok": True}
    assert sleeps == [2.0]


async def test_gives_up_after_max_retries():
    sleeps: list[float] = []
    graph, _ = _client(lambda r: httpx.Response(503, headers={"Retry-After": "60"}), sleeps)

    with pytest.raises(UpstreamUnavailable):
        await graph.get_json(USER, "me")
    assert sleeps == [5.0, 5.0]


async def test_timeout_is_upstream_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    graph, _ = _client(handler)

    with pytest.raises(UpstreamUnavailable):
        await graph.get_json(USER, "me")


async def test_non_object_payload_is_rejected():
    graph, _ = _client(lambda r: httpx.Response(200, json=[1, 2]))

    with pytest.raises(UpstreamUnavailable):
        await graph.get_json(USER, "me")
