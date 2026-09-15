"""Testes do MCPServer em memória (sem HTTP; o cliente in-process não passa pela autenticação)."""

import pytest
from mcp import Client

from ui_genai_mcp.core.errors import ConfigurationError
from ui_genai_mcp.core.services import Services
from ui_genai_mcp.mcp_server import build_mcp
from ui_genai_mcp.toolsets.registry import select_toolsets

pytestmark = pytest.mark.anyio


@pytest.fixture
async def dev_client(dev_settings):
    services = Services.create(dev_settings)
    try:
        async with Client(build_mcp(dev_settings, services), raise_exceptions=True) as client:
            yield client
    finally:
        await services.aclose()


async def test_lists_diagnostic_tools(dev_client):
    tools = {tool.name: tool for tool in (await dev_client.list_tools()).tools}

    assert set(tools) == {"diag_whoami", "diag_sharepoint_probe"}
    assert tools["diag_whoami"].annotations is not None
    assert tools["diag_whoami"].annotations.read_only_hint is True
    assert tools["diag_whoami"].output_schema is not None


async def test_whoami_returns_dev_user_in_dev_mode(dev_client):
    result = await dev_client.call_tool("diag_whoami", {})

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["upn"] == "dev@localhost"
    assert result.structured_content["auth_enabled"] is False


async def test_probe_explains_unavailability_without_auth(dev_client):
    result = await dev_client.call_tool("diag_sharepoint_probe", {})

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["etapa_falha"] == "configuracao"


def test_unknown_toolset_fails_fast():
    with pytest.raises(ConfigurationError, match="inexistente"):
        select_toolsets(["diagnostico", "inexistente"])
