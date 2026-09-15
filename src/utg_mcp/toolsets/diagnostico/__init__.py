"""Toolset de diagnóstico (Fase 0): valida identidade, OBO e acesso ao SharePoint."""

from utg_mcp.toolsets.base import ToolsetSpec
from utg_mcp.toolsets.diagnostico.tools import register

TOOLSET = ToolsetSpec(
    name="diagnostico",
    description="Ferramentas de diagnóstico de autenticação e integrações (não usar em produção).",
    register=register,
)
