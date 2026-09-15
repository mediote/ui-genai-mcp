"""Composition root: app Starlette que hospeda o MCP (Streamable HTTP, stateless) na raiz.

O MCP é montado em "/" (e não num subcaminho) porque o Protected Resource Metadata
(RFC 9728) é servido pelo sub-app em `/.well-known/oauth-protected-resource/mcp`.
As rotas de health vêm ANTES do mount para terem precedência.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from utg_mcp.auth.current_user import CurrentUser
from utg_mcp.core.logging import setup_logging
from utg_mcp.core.request_context import RequestContextMiddleware
from utg_mcp.core.services import Services
from utg_mcp.core.settings import AppSettings, get_settings
from utg_mcp.mcp_server import build_mcp


async def healthz(request: Request) -> JSONResponse:
    """Liveness: processo de pé. Não verifica dependências."""
    return JSONResponse({"status": "ok"})


async def readyz(request: Request) -> JSONResponse:
    """Readiness: lifespan concluído (session manager MCP ativo)."""
    if getattr(request.app.state, "ready", False):
        return JSONResponse({"status": "ready"})
    return JSONResponse({"status": "starting"}, status_code=503)


def create_app(
    settings: AppSettings,
    services: Services | None = None,
    *,
    current_user: Callable[[], CurrentUser] | None = None,
) -> Starlette:
    services = services or Services.create(settings)
    mcp = build_mcp(settings, services, current_user=current_user)
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=settings.mcp_json_response,
        max_request_body_size=settings.max_request_body_bytes,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=settings.allowed_hosts,
            allowed_origins=settings.allowed_origins,
        ),
    )

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        # Sub-apps montados não executam lifespan: o host precisa iniciar o session manager.
        async with mcp.session_manager.run():
            app.state.ready = True
            try:
                yield
            finally:
                app.state.ready = False
                await services.aclose()

    app = Starlette(
        routes=[
            Route("/healthz", healthz, methods=["GET"]),
            Route("/readyz", readyz, methods=["GET"]),
            Mount("/", app=mcp_app),
        ],
        middleware=[Middleware(RequestContextMiddleware)],
        lifespan=lifespan,
    )
    app.state.ready = False
    return app


def app_factory() -> Starlette:
    """Entrypoint do uvicorn (`--factory`): lê configuração do ambiente e configura logging."""
    settings = get_settings()
    setup_logging(settings.log_level)
    return create_app(settings)
