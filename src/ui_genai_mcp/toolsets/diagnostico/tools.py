from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import quote

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from ui_genai_mcp import __version__
from ui_genai_mcp.auth.current_user import CurrentUser
from ui_genai_mcp.core.errors import AppError, UpstreamUnavailable
from ui_genai_mcp.integrations.graph import GraphClient
from ui_genai_mcp.toolsets._shared import READ_ONLY_CLOSED, tool_invocation
from ui_genai_mcp.toolsets.base import ToolsetContext
from ui_genai_mcp.toolsets.diagnostico.models import (
    EchoResult,
    ServerInfoResult,
    SharePointProbeResult,
    WhoAmIResult,
)
from ui_genai_mcp.toolsets.diagnostico.settings import SharePointSettings


def register(mcp: MCPServer, ctx: ToolsetContext) -> None:
    sharepoint = SharePointSettings()

    @mcp.tool(
        name="diag_whoami",
        title="Diagnóstico: quem sou eu",
        description=(
            "Retorna a identidade com que o servidor MCP recebeu esta chamada (nome, UPN, "
            "versão do token e scopes). Use apenas para diagnóstico de autenticação."
        ),
        annotations=READ_ONLY_CLOSED,
    )
    async def diag_whoami() -> WhoAmIResult:
        async with tool_invocation(ctx, "diag_whoami") as user:
            display = user.name or user.upn or "usuário desconhecido"
            return WhoAmIResult(
                user_ref=user.user_ref,
                nome=user.name,
                upn=user.upn,
                tenant_id=user.tenant_id,
                client_app_id=user.client_app_id,
                token_version=user.token_version,
                audience=user.audience,
                scopes=list(user.scopes),
                auth_enabled=ctx.settings.auth_enabled,
                mensagem=f"Chamada recebida em nome de {display}.",
            )

    @mcp.tool(
        name="diag_sharepoint_probe",
        title="Diagnóstico: acesso ao SharePoint",
        description=(
            "Valida a cadeia OBO -> Microsoft Graph -> SharePoint com a identidade do usuário: "
            "perfil (/me), site, biblioteca e arquivo configurados. Use apenas para diagnóstico."
        ),
        annotations=READ_ONLY_CLOSED,
    )
    async def diag_sharepoint_probe() -> SharePointProbeResult:
        async with tool_invocation(ctx, "diag_sharepoint_probe") as user:
            if ctx.services.graph is None:
                return SharePointProbeResult(
                    etapa_falha="configuracao",
                    mensagem=(
                        "Sonda indisponível com AUTH_ENABLED=false (sem token de usuário para OBO)."
                    ),
                )
            return await probe_sharepoint(ctx.services.graph, user, sharepoint)

    @mcp.tool(
        name="diag_echo",
        title="Diagnóstico: eco",
        description=(
            "Devolve a mensagem enviada junto com o tamanho e o horário de processamento no "
            "servidor. Use para validar conectividade e a passagem de argumentos ponta a ponta."
        ),
        annotations=READ_ONLY_CLOSED,
    )
    async def diag_echo(
        mensagem: Annotated[str, Field(description="Texto a ser ecoado de volta.")],
    ) -> EchoResult:
        async with tool_invocation(ctx, "diag_echo") as user:
            return EchoResult(
                mensagem=mensagem,
                tamanho=len(mensagem),
                recebido_em=datetime.now(UTC).isoformat(),
                user_ref=user.user_ref,
            )

    @mcp.tool(
        name="diag_context_info",
        title="Diagnóstico: informações do servidor",
        description=(
            "Retorna metadados não-sensíveis do servidor MCP e da sessão atual (nome, versão, "
            "ambiente, toolsets habilitados e hora do servidor). Use apenas para diagnóstico."
        ),
        annotations=READ_ONLY_CLOSED,
    )
    async def diag_context_info() -> ServerInfoResult:
        async with tool_invocation(ctx, "diag_context_info") as user:
            return ServerInfoResult(
                servidor="ui-genai-mcp",
                versao=__version__,
                ambiente=ctx.settings.environment,
                auth_enabled=ctx.settings.auth_enabled,
                toolsets_habilitados=list(ctx.settings.enabled_toolsets),
                user_ref=user.user_ref,
                hora_servidor=datetime.now(UTC).isoformat(),
            )


async def probe_sharepoint(
    graph: GraphClient, user: CurrentUser, sp: SharePointSettings
) -> SharePointProbeResult:
    result = SharePointProbeResult()

    # /me exige User.Read delegado; falha aqui não impede testar o SharePoint.
    try:
        me = await graph.get_json(user, "me", params={"$select": "displayName"})
        result.graph_me_ok = True
        result.graph_display_name = me.get("displayName")
    except AppError as exc:
        result.graph_me_ok = False
        result.erro = type(exc).__name__

    step = "sharepoint_site"
    try:
        site_path = quote(sp.sp_site_path.strip("/"))
        site = await graph.get_json(
            user, f"sites/{sp.sp_hostname}:/{site_path}", params={"$select": "id,displayName"}
        )
        site_id = site.get("id")
        if not site_id:
            raise UpstreamUnavailable("site_without_id")
        result.sharepoint_site_ok = True

        step = "sharepoint_library"
        drives = await graph.get_json(
            user, f"sites/{site_id}/drives", params={"$select": "id,name"}
        )
        drive = next((d for d in drives.get("value", []) if d.get("name") == sp.sp_library), None)
        if drive is None:
            result.sharepoint_library_ok = False
            result.etapa_falha = step
            result.mensagem = f"Biblioteca '{sp.sp_library}' não encontrada ou sem acesso."
            return result
        result.sharepoint_library_ok = True

        step = "sharepoint_file"
        item = await graph.get_json(
            user,
            f"drives/{drive['id']}/root:/{quote(sp.sp_file_name)}",
            params={"$select": "id,size,lastModifiedDateTime"},
        )
        result.sharepoint_file_ok = True
        result.file_size_bytes = item.get("size")
        result.file_last_modified = item.get("lastModifiedDateTime")
    except AppError as exc:
        result.etapa_falha = step
        result.erro = type(exc).__name__
        result.mensagem = f"Falha na etapa '{step}': {exc.user_message}"
        return result

    result.mensagem = "OBO, Graph e acesso ao arquivo configurado validados com sucesso."
    return result
