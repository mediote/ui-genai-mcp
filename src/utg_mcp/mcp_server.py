"""Montagem do MCPServer: autenticação (resource server) + registro dos toolsets habilitados."""

import logging
from collections.abc import Callable
from functools import partial

from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from pydantic import AnyHttpUrl

from utg_mcp import __version__
from utg_mcp.auth.current_user import CurrentUser, resolve_current_user
from utg_mcp.core.services import Services
from utg_mcp.core.settings import AppSettings
from utg_mcp.toolsets.base import ToolsetContext
from utg_mcp.toolsets.registry import select_toolsets

logger = logging.getLogger(__name__)

SERVER_INSTRUCTIONS = (
    "Servidor MCP corporativo da Ultragaz. Todas as ferramentas atuam com a identidade e as "
    "permissões do usuário autenticado. Responda somente com base no retorno das ferramentas, "
    "sem inventar dados, e respeite a LGPD (não expor dados pessoais sensíveis)."
)


def build_mcp(
    settings: AppSettings,
    services: Services,
    *,
    current_user: Callable[[], CurrentUser] | None = None,
) -> MCPServer:
    auth: AuthSettings | None = None
    if settings.auth_enabled:
        auth = AuthSettings(
            issuer_url=AnyHttpUrl(settings.issuer_v2),
            resource_server_url=AnyHttpUrl(settings.resource_server_url),
            required_scopes=[settings.required_scope_uri],
            # Entra não emite indicador RFC 8707; o verifier já valida `aud`.
            validate_token_resource=False,
        )

    mcp = MCPServer(
        name="utg-genai-mcp",
        title="UTG GenAI MCP",
        version=__version__,
        instructions=SERVER_INSTRUCTIONS,
        token_verifier=services.token_verifier if auth else None,
        auth=auth,
        log_level=settings.log_level,
    )

    resolver = current_user or partial(resolve_current_user, auth_enabled=settings.auth_enabled)
    for spec in select_toolsets(settings.enabled_toolsets):
        spec.register(
            mcp,
            ToolsetContext(
                settings=settings, services=services, current_user=resolver, toolset=spec
            ),
        )
        logger.info("toolset_registered", extra={"toolset": spec.name})
    return mcp
