"""Guarda de contrato das tools: nomes, schemas e annotations são API pública para os agentes.

Mudou uma tool de propósito? Regenere e revise o diff:
    UPDATE_CONTRACTS=1 uv run pytest tests/contract
"""

import json
import os
from pathlib import Path

import pytest
from mcp import Client

from utg_mcp.core.services import Services
from utg_mcp.core.settings import AppSettings
from utg_mcp.mcp_server import build_mcp
from utg_mcp.toolsets._shared import TOOL_NAME_PATTERN
from utg_mcp.toolsets.registry import ALL_TOOLSETS

pytestmark = pytest.mark.anyio

SNAPSHOT = Path(__file__).parent / "snapshots" / "tools.json"


async def _all_tools() -> list[dict[str, object]]:
    settings = AppSettings(
        _env_file=None, auth_enabled=False, enabled_toolsets=[t.name for t in ALL_TOOLSETS]
    )
    services = Services.create(settings)
    try:
        async with Client(build_mcp(settings, services)) as client:
            tools = (await client.list_tools()).tools
    finally:
        await services.aclose()
    return sorted(
        (
            tool.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
                include={
                    "name",
                    "title",
                    "description",
                    "input_schema",
                    "output_schema",
                    "annotations",
                },
            )
            for tool in tools
        ),
        key=lambda t: str(t["name"]),
    )


async def test_tool_contracts_match_snapshot():
    current = await _all_tools()
    rendered = json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if os.environ.get("UPDATE_CONTRACTS") == "1":
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(rendered, encoding="utf-8")

    assert SNAPSHOT.exists(), "Snapshot ausente: rode com UPDATE_CONTRACTS=1 e revise o arquivo."
    assert SNAPSHOT.read_text(encoding="utf-8") == rendered, (
        "Contrato de tools mudou. Se intencional, rode UPDATE_CONTRACTS=1 e revise o diff."
    )


async def test_tool_names_are_valid_unique_and_documented():
    tools = await _all_tools()
    names = [str(t["name"]) for t in tools]

    assert len(names) == len(set(names))
    for tool in tools:
        assert TOOL_NAME_PATTERN.match(str(tool["name"])), tool["name"]
        assert tool.get("description"), f"{tool['name']} sem descrição"
        assert tool.get("title"), f"{tool['name']} sem título"
        assert tool.get("outputSchema"), f"{tool['name']} sem outputSchema"
        annotations = tool.get("annotations")
        assert isinstance(annotations, dict), f"{tool['name']} sem annotations"
        assert "readOnlyHint" in annotations, f"{tool['name']} deve declarar readOnlyHint"
