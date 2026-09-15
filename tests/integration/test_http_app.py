"""Testes no nível HTTP/ASGI: auth (401/403/PRM), transport security e chamada ponta a ponta."""

import httpx
import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from support import CLIENT_ID, PUBLIC_BASE_URL, REQUIRED_SCOPE_URI, TENANT_ID, FakeTokenProvider
from utg_mcp.app import create_app
from utg_mcp.auth.verifier import EntraTokenVerifier
from utg_mcp.core.services import Services

pytestmark = pytest.mark.anyio

MCP_HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
LIST_TOOLS = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}


@pytest.fixture
async def app(auth_settings, key_resolver):
    verifier = EntraTokenVerifier(
        tenant_id=TENANT_ID, client_id=CLIENT_ID, key_resolver=key_resolver
    )
    services = Services.create(
        auth_settings, token_verifier=verifier, token_provider=FakeTokenProvider()
    )
    application = create_app(auth_settings, services)
    async with application.router.lifespan_context(application):
        yield application


def _http(app, base_url: str = PUBLIC_BASE_URL, **headers: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=base_url, headers=headers
    )


async def test_health_endpoints_do_not_require_auth(app):
    async with _http(app) as client:
        live = await client.get("/healthz")
        ready = await client.get("/readyz")

    assert live.status_code == 200
    assert ready.json() == {"status": "ready"}
    assert live.headers["x-request-id"]


async def test_mcp_without_token_returns_401_with_resource_metadata(app):
    async with _http(app) as client:
        response = await client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS)

    assert response.status_code == 401
    challenge = response.headers["www-authenticate"]
    assert challenge.startswith("Bearer ")
    assert (
        f'resource_metadata="{PUBLIC_BASE_URL}/.well-known/oauth-protected-resource/mcp"'
        in challenge
    )


async def test_protected_resource_metadata_is_served_at_root(app):
    async with _http(app) as client:
        response = await client.get("/.well-known/oauth-protected-resource/mcp")

    assert response.status_code == 200
    metadata = response.json()
    assert metadata["resource"] == f"{PUBLIC_BASE_URL}/mcp"
    assert metadata["authorization_servers"] == [
        f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"
    ]
    assert metadata["scopes_supported"] == [REQUIRED_SCOPE_URI]


async def test_invalid_token_returns_401(app, make_token):
    async with _http(
        app, authorization=f"Bearer {make_token(aud='https://graph.microsoft.com')}"
    ) as client:
        response = await client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS)

    assert response.status_code == 401


async def test_token_without_required_scope_returns_403(app, make_token):
    async with _http(app, authorization=f"Bearer {make_token(scp='Outro.Scope')}") as client:
        response = await client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS)

    assert response.status_code == 403
    assert 'error="insufficient_scope"' in response.headers["www-authenticate"]


async def test_unexpected_host_is_rejected(app, make_token):
    async with _http(
        app, base_url="https://evil.test", authorization=f"Bearer {make_token()}"
    ) as client:
        response = await client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS)

    assert response.status_code == 421


async def test_end_to_end_tool_call_sees_authenticated_user(app, make_token):
    http_client = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url=PUBLIC_BASE_URL,
        headers={"Authorization": f"Bearer {make_token()}"},
    )
    async with (
        http_client,
        Client(streamable_http_client(f"{PUBLIC_BASE_URL}/mcp", http_client=http_client)) as client,
    ):
        tools = await client.list_tools()
        result = await client.call_tool("diag_whoami", {})

    assert {tool.name for tool in tools.tools} == {"diag_whoami", "diag_sharepoint_probe"}
    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["upn"] == "ana.teste@example.com"
    assert result.structured_content["scopes"] == [REQUIRED_SCOPE_URI]
    assert result.structured_content["auth_enabled"] is True
