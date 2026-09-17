"""Toolset de clima: condições atuais e previsão via Open-Meteo (API pública, sem chave)."""

from ui_genai_mcp.toolsets.base import ToolsetSpec
from ui_genai_mcp.toolsets.clima.tools import register

TOOLSET = ToolsetSpec(
    name="clima",
    description="Ferramentas de clima (condições atuais e previsão) via Open-Meteo.",
    register=register,
)
