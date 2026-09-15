"""Cliente MCP de fumaça (substitui o MCP Inspector quando não há Node).

Exemplos:
    uv run python scripts/smoke_mcp.py --url http://127.0.0.1:8000/mcp
    MCP_TOKEN=... uv run python scripts/smoke_mcp.py --url https://<fqdn>/mcp --tool diag_whoami
"""

import argparse
import asyncio
import json
import os

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def run(url: str, token: str | None, tool: str | None, arguments: dict[str, object]) -> None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with (
        httpx2.AsyncClient(headers=headers, timeout=60) as http,
        Client(streamable_http_client(url, http_client=http)) as client,
    ):
        tools = (await client.list_tools()).tools
        print(f"{len(tools)} tools:")
        for item in tools:
            print(f"  - {item.name}: {item.title or ''}")

        if tool:
            result = await client.call_tool(tool, arguments)
            print(
                json.dumps(
                    {
                        "is_error": result.is_error,
                        "structured_content": result.structured_content,
                        "content": [block.model_dump(mode="json") for block in result.content],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--token", default=os.environ.get("MCP_TOKEN"))
    parser.add_argument("--tool")
    parser.add_argument("--args", default="{}", help="JSON com os argumentos da tool")
    ns = parser.parse_args()
    asyncio.run(run(ns.url, ns.token, ns.tool, json.loads(ns.args)))


if __name__ == "__main__":
    main()
