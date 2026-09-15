import pytest
from pydantic import SecretStr, ValidationError

from support import CLIENT_ID, TENANT_ID
from ui_genai_mcp.core.settings import AppSettings


def _auth_kwargs() -> dict[str, object]:
    return {
        "azure_ad_tenant_id": TENANT_ID,
        "azure_ad_client_id": CLIENT_ID,
        "azure_ad_client_secret": SecretStr("s"),
        "public_base_url": "https://mcp.test/",
    }


def test_auth_disabled_is_rejected_in_production():
    with pytest.raises(ValidationError, match="AUTH_ENABLED=false"):
        AppSettings(_env_file=None, environment="prd", auth_enabled=False)


def test_auth_enabled_requires_entra_configuration():
    with pytest.raises(ValidationError) as exc_info:
        AppSettings(_env_file=None, auth_enabled=True, azure_ad_tenant_id=TENANT_ID)

    message = str(exc_info.value)
    assert "AZURE_AD_CLIENT_ID" in message
    assert "AZURE_AD_CLIENT_SECRET" in message
    assert "PUBLIC_BASE_URL" in message


def test_diagnostics_toolset_requires_explicit_opt_in_in_production():
    with pytest.raises(ValidationError, match="diagnostico"):
        AppSettings(
            _env_file=None, environment="prd", enabled_toolsets=["diagnostico"], **_auth_kwargs()
        )

    settings = AppSettings(
        _env_file=None,
        environment="prd",
        enabled_toolsets=["diagnostico"],
        allow_diagnostics_in_prd=True,
        **_auth_kwargs(),
    )
    assert settings.enabled_toolsets == ["diagnostico"]


def test_csv_lists_are_parsed_from_environment(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("ENABLED_TOOLSETS", "diagnostico, exemplo ,")
    monkeypatch.setenv("ALLOWED_HOSTS", "mcp.test,localhost:*")

    settings = AppSettings(_env_file=None)

    assert settings.enabled_toolsets == ["diagnostico", "exemplo"]
    assert settings.allowed_hosts == ["mcp.test", "localhost:*"]


def test_derived_entra_values():
    settings = AppSettings(_env_file=None, **_auth_kwargs())

    assert settings.api_audience == f"api://{CLIENT_ID}"
    assert settings.required_scope_uri == f"api://{CLIENT_ID}/access_as_user"
    assert settings.issuer_v2 == f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"
    assert settings.resource_server_url == "https://mcp.test/mcp"
