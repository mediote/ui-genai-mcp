from pydantic import BaseModel, Field


class ClimaAtualResult(BaseModel):
    """Condições atuais de uma localidade."""

    cidade: str = Field(description="Nome da localidade resolvida.")
    pais: str | None = Field(default=None, description="País da localidade.")
    latitude: float
    longitude: float
    temperatura_c: float = Field(description="Temperatura atual em graus Celsius.")
    sensacao_c: float | None = Field(default=None, description="Sensação térmica em Celsius.")
    umidade_pct: int | None = Field(default=None, description="Umidade relativa do ar (%).")
    vento_kmh: float | None = Field(default=None, description="Velocidade do vento (km/h).")
    condicao: str = Field(description="Descrição do tempo em pt-BR.")
    observado_em: str = Field(description="Instante da observação (ISO 8601, fuso local).")


class DiaPrevisao(BaseModel):
    """Previsão consolidada de um dia."""

    data: str = Field(description="Data do dia (YYYY-MM-DD).")
    temp_min_c: float | None = Field(default=None, description="Temperatura mínima (°C).")
    temp_max_c: float | None = Field(default=None, description="Temperatura máxima (°C).")
    prob_chuva_pct: int | None = Field(
        default=None, description="Probabilidade máxima de precipitação no dia (%)."
    )
    condicao: str = Field(description="Descrição do tempo em pt-BR.")


class ClimaPrevisaoResult(BaseModel):
    """Previsão diária de uma localidade."""

    cidade: str = Field(description="Nome da localidade resolvida.")
    pais: str | None = Field(default=None, description="País da localidade.")
    latitude: float
    longitude: float
    dias: list[DiaPrevisao] = Field(description="Previsão diária, em ordem cronológica.")
