"""Middleware ASGI puro: request id + log de acesso sem query string.

ASGI puro (não `BaseHTTPMiddleware`) para não interferir no streaming do transporte MCP.
"""

import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ui_genai_mcp.core.logging import request_id_var

logger = logging.getLogger("ui_genai_mcp.access")

_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_QUIET_PATHS = frozenset({"/healthz", "/readyz"})


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = _header(scope, b"x-request-id")
        request_id = (
            incoming if incoming and _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        )
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = scope.get("path", "")
            if path not in _QUIET_PATHS:
                logger.info(
                    "http_request",
                    extra={
                        "method": scope.get("method"),
                        "path": path,
                        "status": status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                        "mcp_protocol_version": _header(scope, b"mcp-protocol-version"),
                    },
                )
            request_id_var.reset(token)


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return str(value.decode("latin-1"))
    return None
