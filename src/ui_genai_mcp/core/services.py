"""Container de serviços compartilhados (criados uma vez por processo, fechados no lifespan)."""

from dataclasses import dataclass

import httpx
from mcp.server.auth.provider import TokenVerifier

from ui_genai_mcp import __version__
from ui_genai_mcp.auth.obo import OboTokenProvider
from ui_genai_mcp.auth.verifier import EntraTokenVerifier, JwksSigningKeyResolver
from ui_genai_mcp.core.errors import ConfigurationError
from ui_genai_mcp.core.settings import AppSettings
from ui_genai_mcp.integrations.graph import DelegatedTokenProvider, GraphClient


@dataclass(slots=True)
class Services:
    http: httpx.AsyncClient
    token_verifier: TokenVerifier | None
    graph: GraphClient | None

    @classmethod
    def create(
        cls,
        settings: AppSettings,
        *,
        token_verifier: TokenVerifier | None = None,
        token_provider: DelegatedTokenProvider | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> "Services":
        http = http or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.graph_timeout_seconds, connect=5.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
            follow_redirects=True,
            headers={"User-Agent": f"ui-genai-mcp/{__version__}"},
        )
        if not settings.auth_enabled:
            return cls(http=http, token_verifier=None, graph=None)

        if token_verifier is None:
            token_verifier = EntraTokenVerifier(
                tenant_id=settings.azure_ad_tenant_id,
                client_id=settings.azure_ad_client_id,
                key_resolver=JwksSigningKeyResolver(settings.jwks_url),
            )
        if token_provider is None:
            if settings.azure_ad_client_secret is None:
                raise ConfigurationError("AZURE_AD_CLIENT_SECRET ausente")
            token_provider = OboTokenProvider.for_entra(
                tenant_id=settings.azure_ad_tenant_id,
                client_id=settings.azure_ad_client_id,
                client_secret=settings.azure_ad_client_secret.get_secret_value(),
            )
        graph = GraphClient(http=http, token_provider=token_provider)
        return cls(http=http, token_verifier=token_verifier, graph=graph)

    async def aclose(self) -> None:
        await self.http.aclose()
