from pydantic import BaseModel, Field


class WhoAmIResult(BaseModel):
    user_ref: str = Field(description="Identificador pseudonimizado do usuário (hash).")
    nome: str = Field(description="Nome do usuário conforme o token.")
    upn: str = Field(description="UPN/e-mail do usuário conforme o token.")
    tenant_id: str
    client_app_id: str = Field(description="App (azp/appid) que obteve o token.")
    token_version: str = Field(description="Versão do token Entra (1.0 ou 2.0).")
    audience: str
    scopes: list[str]
    auth_enabled: bool
    mensagem: str


class SharePointProbeResult(BaseModel):
    graph_me_ok: bool | None = None
    graph_display_name: str | None = None
    sharepoint_site_ok: bool | None = None
    sharepoint_library_ok: bool | None = None
    sharepoint_file_ok: bool | None = None
    file_size_bytes: int | None = None
    file_last_modified: str | None = None
    etapa_falha: str | None = Field(default=None, description="Etapa em que a sonda falhou.")
    erro: str | None = Field(default=None, description="Tipo do erro (sem detalhes sensíveis).")
    mensagem: str = ""
