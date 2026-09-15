from pydantic_settings import BaseSettings, SettingsConfigDict


class OrganogramaSettings(BaseSettings):
    """Coordenadas do Organograma.json no SharePoint (antes hard-coded em botjao.py)."""

    model_config = SettingsConfigDict(
        env_prefix="ORGANOGRAMA_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    sp_hostname: str = "grupoultracloud.sharepoint.com"
    sp_site_path: str = "/sites/ug-base_conhecimento_genai"
    sp_library: str = "base_RH_Organograma"
    sp_file_name: str = "Organograma.json"
