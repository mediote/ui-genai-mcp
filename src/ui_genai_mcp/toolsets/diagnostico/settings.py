from pydantic_settings import BaseSettings, SettingsConfigDict


class SharePointSettings(BaseSettings):
    """Coordenadas de um arquivo alvo no SharePoint, usadas pela sonda de diagnóstico.

    Configuradas por ambiente (prefixo `SHAREPOINT_`). Sem valores padrão de negócio:
    preencha conforme o site/biblioteca/arquivo que a sonda deve validar.
    """

    model_config = SettingsConfigDict(
        env_prefix="SHAREPOINT_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    sp_hostname: str = ""
    sp_site_path: str = ""
    sp_library: str = ""
    sp_file_name: str = ""
