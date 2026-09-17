from typing import Annotated, Any

import httpx
from mcp.server.mcpserver import MCPServer
from pydantic import Field

from ui_genai_mcp.core.errors import ResourceNotFound, UpstreamUnavailable
from ui_genai_mcp.toolsets._shared import READ_ONLY_OPEN, tool_invocation
from ui_genai_mcp.toolsets.base import ToolsetContext
from ui_genai_mcp.toolsets.clima.domain import descrever_tempo
from ui_genai_mcp.toolsets.clima.models import (
    ClimaAtualResult,
    ClimaPrevisaoResult,
    DiaPrevisao,
)
from ui_genai_mcp.toolsets.clima.settings import ClimaSettings


def register(mcp: MCPServer, ctx: ToolsetContext) -> None:
    clima = ClimaSettings()

    @mcp.tool(
        name="clima_atual",
        title="Clima: condições atuais",
        description=(
            "Retorna as condições meteorológicas atuais de uma cidade (temperatura, sensação "
            "térmica, umidade, vento e descrição do tempo). Fonte: Open-Meteo (pública)."
        ),
        annotations=READ_ONLY_OPEN,
    )
    async def clima_atual(
        cidade: Annotated[str, Field(description="Nome da cidade, ex.: 'São Paulo' ou 'Lisboa'.")],
    ) -> ClimaAtualResult:
        async with tool_invocation(ctx, "clima_atual"):
            return await buscar_clima_atual(ctx.services.http, clima, cidade)

    @mcp.tool(
        name="clima_previsao",
        title="Clima: previsão dos próximos dias",
        description=(
            "Retorna a previsão diária de uma cidade (mínima, máxima, probabilidade de chuva e "
            "descrição do tempo) para os próximos dias. Fonte: Open-Meteo (pública)."
        ),
        annotations=READ_ONLY_OPEN,
    )
    async def clima_previsao(
        cidade: Annotated[str, Field(description="Nome da cidade, ex.: 'São Paulo' ou 'Lisboa'.")],
        dias: Annotated[
            int, Field(ge=1, le=16, description="Quantidade de dias a prever (1 a 16).")
        ] = 3,
    ) -> ClimaPrevisaoResult:
        async with tool_invocation(ctx, "clima_previsao"):
            return await buscar_previsao(ctx.services.http, clima, cidade, dias)


async def _get_json(http: httpx.AsyncClient, url: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        response = await http.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as exc:
        raise UpstreamUnavailable(f"open_meteo_{exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise UpstreamUnavailable(f"open_meteo_transport:{type(exc).__name__}") from exc
    except ValueError as exc:
        raise UpstreamUnavailable("open_meteo_invalid_json") from exc
    if not isinstance(data, dict):
        raise UpstreamUnavailable("open_meteo_unexpected_payload")
    return data


async def _geocode(http: httpx.AsyncClient, sp: ClimaSettings, cidade: str) -> dict[str, Any]:
    """Resolve o nome da cidade em coordenadas (primeiro resultado)."""
    data = await _get_json(
        http,
        sp.geocoding_url,
        {"name": cidade, "count": 1, "language": sp.language, "format": "json"},
    )
    results = data.get("results")
    if not results:
        # Sem o termo pesquisado no detalhe técnico: `str(exc)` vai para o log (LGPD).
        # A cidade só aparece no `user_message`, que não é logado.
        raise ResourceNotFound(
            "cidade_nao_encontrada",
            user_message=f"Não encontrei a cidade '{cidade}'. Verifique o nome e tente novamente.",
        )
    first = results[0]
    if not isinstance(first, dict):
        raise UpstreamUnavailable("open_meteo_unexpected_geocode")
    return first


def _at[T](values: list[T] | None, index: int) -> T | None:
    """Retorna values[index] se a lista existir e tiver esse índice; senão None."""
    if values is not None and index < len(values):
        return values[index]
    return None


async def buscar_clima_atual(
    http: httpx.AsyncClient, sp: ClimaSettings, cidade: str
) -> ClimaAtualResult:
    local = await _geocode(http, sp, cidade)
    data = await _get_json(
        http,
        sp.forecast_url,
        {
            "latitude": local["latitude"],
            "longitude": local["longitude"],
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "weather_code,wind_speed_10m"
            ),
            "timezone": sp.timezone,
        },
    )
    current = data.get("current", {})
    temperatura = current.get("temperature_2m")
    if temperatura is None:
        raise UpstreamUnavailable("open_meteo_sem_condicao_atual")
    return ClimaAtualResult(
        cidade=str(local.get("name") or cidade),
        pais=local.get("country"),
        latitude=float(local["latitude"]),
        longitude=float(local["longitude"]),
        temperatura_c=float(temperatura),
        sensacao_c=current.get("apparent_temperature"),
        umidade_pct=current.get("relative_humidity_2m"),
        vento_kmh=current.get("wind_speed_10m"),
        condicao=descrever_tempo(current.get("weather_code")),
        observado_em=str(current.get("time", "")),
    )


async def buscar_previsao(
    http: httpx.AsyncClient, sp: ClimaSettings, cidade: str, dias: int
) -> ClimaPrevisaoResult:
    dias = max(1, min(dias, sp.max_dias_previsao))
    local = await _geocode(http, sp, cidade)
    data = await _get_json(
        http,
        sp.forecast_url,
        {
            "latitude": local["latitude"],
            "longitude": local["longitude"],
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
            ),
            "forecast_days": dias,
            "timezone": sp.timezone,
        },
    )
    daily = data.get("daily", {})
    datas = daily.get("time", [])
    previsao = [
        DiaPrevisao(
            data=str(datas[i]),
            temp_min_c=_at(daily.get("temperature_2m_min"), i),
            temp_max_c=_at(daily.get("temperature_2m_max"), i),
            prob_chuva_pct=_at(daily.get("precipitation_probability_max"), i),
            condicao=descrever_tempo(_at(daily.get("weather_code"), i)),
        )
        for i in range(len(datas) if isinstance(datas, list) else 0)
    ]
    return ClimaPrevisaoResult(
        cidade=str(local.get("name") or cidade),
        pais=local.get("country"),
        latitude=float(local["latitude"]),
        longitude=float(local["longitude"]),
        dias=previsao,
    )
