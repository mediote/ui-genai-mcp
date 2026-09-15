from dataclasses import replace

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from support import CLIENT_ID
from ui_genai_mcp.auth.current_user import DEV_USER, CurrentUser
from ui_genai_mcp.core.errors import AuthenticationRequired, PermissionDenied
from ui_genai_mcp.core.services import Services
from ui_genai_mcp.toolsets._shared import FORBIDDEN_MESSAGE, tool_invocation
from ui_genai_mcp.toolsets.base import ToolsetContext, ToolsetSpec

pytestmark = pytest.mark.anyio


def _ctx(
    settings,
    *,
    user: CurrentUser = DEV_USER,
    scopes: frozenset[str] = frozenset(),
    fail_user: bool = False,
):
    def current_user() -> CurrentUser:
        if fail_user:
            raise AuthenticationRequired("missing")
        return user

    spec = ToolsetSpec(
        name="teste", description="", register=lambda mcp, ctx: None, required_scopes=scopes
    )
    services = Services(http=httpx.AsyncClient(), token_verifier=None, graph=None)
    return ToolsetContext(
        settings=settings, services=services, current_user=current_user, toolset=spec
    )


async def test_yields_current_user(dev_settings):
    async with tool_invocation(_ctx(dev_settings), "tool") as user:
        assert user is DEV_USER


async def test_app_error_becomes_friendly_tool_error(dev_settings):
    with pytest.raises(ToolError, match="permissão para acessar"):
        async with tool_invocation(_ctx(dev_settings), "tool"):
            raise PermissionDenied("graph_403 detalhe técnico")


async def test_missing_user_becomes_tool_error(auth_settings):
    with pytest.raises(ToolError, match="Faça login novamente"):
        async with tool_invocation(_ctx(auth_settings, fail_user=True), "tool"):
            pass


async def test_toolset_scope_is_enforced_when_auth_enabled(auth_settings):
    user = replace(DEV_USER, scopes=(f"api://{CLIENT_ID}/access_as_user",))
    ctx = _ctx(auth_settings, user=user, scopes=frozenset({"Org.Read"}))

    with pytest.raises(ToolError, match=FORBIDDEN_MESSAGE):
        async with tool_invocation(ctx, "tool"):
            pass

    allowed = replace(user, scopes=(*user.scopes, f"api://{CLIENT_ID}/Org.Read"))
    async with tool_invocation(
        _ctx(auth_settings, user=allowed, scopes=frozenset({"Org.Read"})), "tool"
    ):
        pass


async def test_unexpected_errors_propagate(dev_settings):
    with pytest.raises(RuntimeError):
        async with tool_invocation(_ctx(dev_settings), "tool"):
            raise RuntimeError("bug")
