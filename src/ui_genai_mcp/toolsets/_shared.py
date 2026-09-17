"""Peças reutilizadas por todos os toolsets: annotations padrão e o envelope de invocação."""

import logging
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from ui_genai_mcp.auth.current_user import CurrentUser
from ui_genai_mcp.core.errors import AppError
from ui_genai_mcp.core.logging import tool_var, user_ref_var
from ui_genai_mcp.toolsets.base import ToolsetContext

logger = logging.getLogger("ui_genai_mcp.tools")

TOOL_NAME_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")
"""Nomes de tools: snake_case, <= 64 chars, sem pontos (vira nome de função no modelo)."""

FORBIDDEN_MESSAGE = "Você não tem permissão para usar esta ferramenta."

READ_ONLY_CLOSED = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
"""Leitura de base interna fechada (fonte corporativa não pública)."""

READ_ONLY_OPEN = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)
"""Leitura de fonte externa pública (ex.: APIs abertas na internet)."""


@asynccontextmanager
async def tool_invocation(ctx: ToolsetContext, tool_name: str) -> AsyncIterator[CurrentUser]:
    """Envelope padrão de toda tool.

    - resolve o usuário autenticado e checa os scopes do toolset;
    - injeta contexto de log (tool, user_ref) e registra outcome/duração;
    - converte `AppError` em `ToolError` com mensagem amigável (pt-BR).

    É um context manager (e não decorator) para não alterar a assinatura da função,
    da qual o SDK deriva o inputSchema.
    """
    tool_token = tool_var.set(tool_name)
    user_token = None
    started = time.perf_counter()
    outcome = "unexpected_error"
    try:
        try:
            user = ctx.current_user()
        except AppError as exc:
            outcome = type(exc).__name__
            raise ToolError(exc.user_message) from exc

        user_token = user_ref_var.set(user.user_ref)
        required = {f"{ctx.settings.api_audience}/{s}" for s in ctx.toolset.required_scopes}
        if ctx.settings.auth_enabled and not user.has_scopes(required):
            outcome = "forbidden"
            raise ToolError(FORBIDDEN_MESSAGE)

        try:
            yield user
        except AppError as exc:
            outcome = type(exc).__name__
            logger.warning("tool_app_error", extra={"error": outcome, "detail": str(exc)})
            raise ToolError(exc.user_message) from exc
        except ToolError:
            outcome = "tool_error"
            raise
        outcome = "ok"
    finally:
        logger.info(
            "tool_call",
            extra={
                "toolset": ctx.toolset.name,
                "outcome": outcome,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        if user_token is not None:
            user_ref_var.reset(user_token)
        tool_var.reset(tool_token)
