import httpx
import pytest

from support import FakeTokenProvider
from ui_genai_mcp.auth.current_user import CurrentUser
from ui_genai_mcp.integrations.graph import GraphClient
from ui_genai_mcp.toolsets.diagnostico.settings import SharePointSettings
from ui_genai_mcp.toolsets.diagnostico.tools import probe_sharepoint

pytestmark = pytest.mark.anyio

USER = CurrentUser("oid", "tid", "Ana", "ana@x", "app", (), "2.0", "aud", assertion="a")
SP = SharePointSettings(
    _env_file=None,
    sp_hostname="contoso.sharepoint.com",
    sp_site_path="/sites/rh",
    sp_library="Docs",
    sp_file_name="Org Chart.json",
)


def _graph(routes: dict[str, httpx.Response]) -> GraphClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(request.url.path, httpx.Response(404))

    return GraphClient(
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        token_provider=FakeTokenProvider(),
    )


async def test_probe_success():
    graph = _graph(
        {
            "/v1.0/me": httpx.Response(200, json={"displayName": "Ana"}),
            "/v1.0/sites/contoso.sharepoint.com:/sites/rh": httpx.Response(
                200, json={"id": "site-1"}
            ),
            "/v1.0/sites/site-1/drives": httpx.Response(
                200, json={"value": [{"id": "d1", "name": "Docs"}]}
            ),
            "/v1.0/drives/d1/root:/Org Chart.json": httpx.Response(
                200, json={"id": "i1", "size": 42, "lastModifiedDateTime": "2026-09-01T00:00:00Z"}
            ),
        }
    )

    result = await probe_sharepoint(graph, USER, SP)

    assert result.graph_me_ok is True
    assert result.sharepoint_site_ok is True
    assert result.sharepoint_library_ok is True
    assert result.sharepoint_file_ok is True
    assert result.file_size_bytes == 42
    assert result.etapa_falha is None


async def test_probe_reports_missing_library_and_continues_after_me_failure():
    graph = _graph(
        {
            "/v1.0/me": httpx.Response(403),
            "/v1.0/sites/contoso.sharepoint.com:/sites/rh": httpx.Response(
                200, json={"id": "site-1"}
            ),
            "/v1.0/sites/site-1/drives": httpx.Response(
                200, json={"value": [{"id": "d1", "name": "Outra"}]}
            ),
        }
    )

    result = await probe_sharepoint(graph, USER, SP)

    assert result.graph_me_ok is False
    assert result.sharepoint_site_ok is True
    assert result.sharepoint_library_ok is False
    assert result.etapa_falha == "sharepoint_library"


async def test_probe_reports_site_permission_denied():
    graph = _graph(
        {
            "/v1.0/me": httpx.Response(200, json={}),
            "/v1.0/sites/contoso.sharepoint.com:/sites/rh": httpx.Response(403),
        }
    )

    result = await probe_sharepoint(graph, USER, SP)

    assert result.etapa_falha == "sharepoint_site"
    assert result.erro == "PermissionDenied"
