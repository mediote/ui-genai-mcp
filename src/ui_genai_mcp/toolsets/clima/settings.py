"""Configuração do toolset de clima (Open-Meteo — API pública, sem chave de API).

Configurável por ambiente (prefixo `CLIMA_`). Os valores padrão apontam para os
endpoints públicos do Open-Meteo e não expõem segredos.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ClimaSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CLIMA_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    geocoding_url: str = "https://geocoding-api.open-meteo.com/v1/search"
    forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    language: str = "pt"
    timezone: str = "auto"
    max_dias_previsao: int = 16
