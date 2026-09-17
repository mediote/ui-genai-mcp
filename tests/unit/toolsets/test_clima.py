import httpx
import pytest

from ui_genai_mcp.core.errors import ResourceNotFound, UpstreamUnavailable
from ui_genai_mcp.toolsets.clima.domain import descrever_tempo
from ui_genai_mcp.toolsets.clima.settings import ClimaSettings
from ui_genai_mcp.toolsets.clima.tools import buscar_clima_atual, buscar_previsao

pytestmark = pytest.mark.anyio

SP = ClimaSettings(_env_file=None)
GEO_SP = {
    "results": [{"name": "São Paulo", "country": "Brasil", "latitude": -23.55, "longitude": -46.63}]
}


def _http(routes: dict[str, httpx.Response]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(request.url.path, httpx.Response(404))

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_descrever_tempo_traduz_codigos():
    assert descrever_tempo(0) == "Céu limpo"
    assert descrever_tempo(61) == "Chuva fraca"
    assert descrever_tempo(None) == "Condição desconhecida"
    assert descrever_tempo(99999) == "Condição desconhecida"


async def test_clima_atual_ok():
    http = _http(
        {
            "/v1/search": httpx.Response(200, json=GEO_SP),
            "/v1/forecast": httpx.Response(
                200,
                json={
                    "current": {
                        "time": "2026-09-15T12:00",
                        "temperature_2m": 25.0,
                        "apparent_temperature": 26.5,
                        "relative_humidity_2m": 60,
                        "weather_code": 1,
                        "wind_speed_10m": 10.0,
                    }
                },
            ),
        }
    )

    result = await buscar_clima_atual(http, SP, "São Paulo")

    assert result.cidade == "São Paulo"
    assert result.pais == "Brasil"
    assert result.temperatura_c == 25.0
    assert result.sensacao_c == 26.5
    assert result.umidade_pct == 60
    assert result.condicao == "Predominantemente limpo"


async def test_clima_previsao_ok_e_respeita_dias():
    http = _http(
        {
            "/v1/search": httpx.Response(200, json=GEO_SP),
            "/v1/forecast": httpx.Response(
                200,
                json={
                    "daily": {
                        "time": ["2026-09-15", "2026-09-16"],
                        "weather_code": [1, 61],
                        "temperature_2m_max": [26.0, 24.0],
                        "temperature_2m_min": [18.0, 17.0],
                        "precipitation_probability_max": [10, 80],
                    }
                },
            ),
        }
    )

    result = await buscar_previsao(http, SP, "São Paulo", dias=2)

    assert len(result.dias) == 2
    assert result.dias[0].temp_max_c == 26.0
    assert result.dias[1].condicao == "Chuva fraca"
    assert result.dias[1].prob_chuva_pct == 80


async def test_clima_atual_cidade_nao_encontrada():
    http = _http({"/v1/search": httpx.Response(200, json={"results": []})})

    with pytest.raises(ResourceNotFound):
        await buscar_clima_atual(http, SP, "Cidade Inexistente 123")


async def test_clima_atual_upstream_indisponivel():
    http = _http(
        {
            "/v1/search": httpx.Response(200, json=GEO_SP),
            "/v1/forecast": httpx.Response(503),
        }
    )

    with pytest.raises(UpstreamUnavailable):
        await buscar_clima_atual(http, SP, "São Paulo")


async def test_nao_encontrada_nao_vaza_cidade_no_detalhe():
    """O termo pesquisado não pode aparecer em str(exc) (vai para o log — LGPD)."""
    http = _http({"/v1/search": httpx.Response(200, json={"results": []})})

    with pytest.raises(ResourceNotFound) as exc_info:
        await buscar_clima_atual(http, SP, "Atlântida Secreta")

    assert "Atlântida Secreta" not in str(exc_info.value)
    assert "Atlântida Secreta" in exc_info.value.user_message


async def test_clima_atual_erro_de_transporte():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with pytest.raises(UpstreamUnavailable):
        await buscar_clima_atual(http, SP, "São Paulo")


async def test_clima_atual_json_invalido():
    http = _http(
        {
            "/v1/search": httpx.Response(
                200, content=b"not json", headers={"content-type": "text/plain"}
            )
        }
    )

    with pytest.raises(UpstreamUnavailable):
        await buscar_clima_atual(http, SP, "São Paulo")


async def test_clima_atual_payload_nao_dict():
    http = _http({"/v1/search": httpx.Response(200, json=["inesperado"])})

    with pytest.raises(UpstreamUnavailable):
        await buscar_clima_atual(http, SP, "São Paulo")


async def test_clima_atual_geocode_nao_dict():
    http = _http({"/v1/search": httpx.Response(200, json={"results": ["não é um objeto"]})})

    with pytest.raises(UpstreamUnavailable):
        await buscar_clima_atual(http, SP, "São Paulo")


async def test_clima_atual_sem_condicao_atual():
    http = _http(
        {
            "/v1/search": httpx.Response(200, json=GEO_SP),
            "/v1/forecast": httpx.Response(200, json={"current": {"time": "2026-09-15T12:00"}}),
        }
    )

    with pytest.raises(UpstreamUnavailable):
        await buscar_clima_atual(http, SP, "São Paulo")


async def test_previsao_lida_com_listas_curtas():
    """Se uma série vier mais curta que `time`, os dias faltantes ficam None (via _at)."""
    http = _http(
        {
            "/v1/search": httpx.Response(200, json=GEO_SP),
            "/v1/forecast": httpx.Response(
                200,
                json={
                    "daily": {
                        "time": ["2026-09-15", "2026-09-16"],
                        "weather_code": [1],
                        "temperature_2m_max": [26.0],
                        "temperature_2m_min": [18.0],
                        "precipitation_probability_max": [10],
                    }
                },
            ),
        }
    )

    result = await buscar_previsao(http, SP, "São Paulo", dias=2)

    assert len(result.dias) == 2
    assert result.dias[1].temp_max_c is None
    assert result.dias[1].condicao == "Condição desconhecida"
