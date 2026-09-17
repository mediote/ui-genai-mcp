"""Configuração da aplicação via variáveis de ambiente (pydantic-settings)."""

from functools import lru_cache
from typing import Annotated, Literal, Self

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

CsvList = Annotated[list[str], NoDecode]


class AppSettings(BaseSettings):
    """Configuração global. Toolsets têm suas próprias classes com `env_prefix`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["dev", "hml", "prd"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Autenticação (Entra ID) — app registration existente reutilizado
    auth_enabled: bool = True
    azure_ad_tenant_id: str = ""
    azure_ad_client_id: str = ""
    azure_ad_client_secret: SecretStr | None = None
    mcp_required_scope: str = Field(
        default="access_as_user",
        description="Nome curto do scope exposto no app registration (claim `scp`).",
    )

    # HTTP / transporte MCP
    public_base_url: AnyHttpUrl | None = None
    allowed_hosts: CsvList = Field(default_factory=lambda: ["localhost:*", "127.0.0.1:*"])
    allowed_origins: CsvList = Field(default_factory=list)
    mcp_json_response: bool = True
    max_request_body_bytes: int = Field(default=1_048_576, gt=0)

    # Integrações
    graph_timeout_seconds: float = Field(default=20.0, gt=0)

    # Toolsets
    enabled_toolsets: CsvList = Field(default_factory=lambda: ["diagnostico", "clima"])
    allow_diagnostics_in_prd: bool = False

    @field_validator("allowed_hosts", "allowed_origins", "enabled_toolsets", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _validate_consistency(self) -> Self:
        if self.environment == "prd" and not self.auth_enabled:
            raise ValueError("AUTH_ENABLED=false não é permitido em ENVIRONMENT=prd.")
        if self.auth_enabled:
            missing = [
                name
                for name, value in (
                    ("AZURE_AD_TENANT_ID", self.azure_ad_tenant_id),
                    ("AZURE_AD_CLIENT_ID", self.azure_ad_client_id),
                    ("AZURE_AD_CLIENT_SECRET", self.azure_ad_client_secret),
                    ("PUBLIC_BASE_URL", self.public_base_url),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"AUTH_ENABLED=true exige: {', '.join(missing)}.")
        if (
            self.environment == "prd"
            and "diagnostico" in self.enabled_toolsets
            and not self.allow_diagnostics_in_prd
        ):
            raise ValueError("Toolset 'diagnostico' em prd exige ALLOW_DIAGNOSTICS_IN_PRD=true.")
        return self

    @property
    def api_audience(self) -> str:
        return f"api://{self.azure_ad_client_id}"

    @property
    def required_scope_uri(self) -> str:
        return f"{self.api_audience}/{self.mcp_required_scope}"

    @property
    def issuer_v2(self) -> str:
        return f"https://login.microsoftonline.com/{self.azure_ad_tenant_id}/v2.0"

    @property
    def jwks_url(self) -> str:
        return f"https://login.microsoftonline.com/{self.azure_ad_tenant_id}/discovery/v2.0/keys"

    @property
    def resource_server_url(self) -> str:
        base = str(self.public_base_url or "http://localhost:8000").rstrip("/")
        return f"{base}/mcp"


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()
