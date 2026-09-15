"""Contrato de um toolset: cada domínio expõe um `ToolsetSpec` com sua função `register`."""

from collections.abc import Callable
from dataclasses import dataclass, field

from mcp.server.mcpserver import MCPServer

from utg_mcp.auth.current_user import CurrentUser
from utg_mcp.core.services import Services
from utg_mcp.core.settings import AppSettings


@dataclass(frozen=True, slots=True)
class ToolsetSpec:
    name: str
    """Identificador usado em ENABLED_TOOLSETS (ex.: "organograma")."""
    description: str
    register: Callable[[MCPServer, "ToolsetContext"], None]
    required_scopes: frozenset[str] = field(default_factory=frozenset)
    """Scopes curtos (claim `scp`) exigidos além do scope global — checados em cada tool."""


@dataclass(frozen=True, slots=True)
class ToolsetContext:
    """Dependências entregues ao `register` de cada toolset."""

    settings: AppSettings
    services: Services
    current_user: Callable[[], CurrentUser]
    toolset: ToolsetSpec
