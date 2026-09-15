"""Registro central e EXPLÍCITO de toolsets.

Para adicionar um toolset: importe seu `TOOLSET` e inclua-o em `ALL_TOOLSETS`.
Sem auto-discovery de propósito — cada inclusão aparece no diff e é revisada.
"""

from collections.abc import Sequence

from ui_genai_mcp.core.errors import ConfigurationError
from ui_genai_mcp.toolsets import diagnostico
from ui_genai_mcp.toolsets.base import ToolsetSpec

ALL_TOOLSETS: tuple[ToolsetSpec, ...] = (diagnostico.TOOLSET,)


def select_toolsets(enabled: Sequence[str]) -> list[ToolsetSpec]:
    by_name = {spec.name: spec for spec in ALL_TOOLSETS}
    unknown = sorted(set(enabled) - by_name.keys())
    if unknown:
        raise ConfigurationError(f"Toolsets desconhecidos em ENABLED_TOOLSETS: {unknown}")
    return [spec for spec in ALL_TOOLSETS if spec.name in enabled]
