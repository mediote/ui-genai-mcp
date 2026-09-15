from collections.abc import Callable
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from support import CLIENT_ID, PUBLIC_BASE_URL, TENANT_ID, StaticKeyResolver, build_claims, sign
from utg_mcp.core.settings import AppSettings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def rsa_private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def key_resolver(rsa_private_key: rsa.RSAPrivateKey) -> StaticKeyResolver:
    return StaticKeyResolver(rsa_private_key.public_key())


@pytest.fixture
def make_token(rsa_private_key: rsa.RSAPrivateKey) -> Callable[..., str]:
    def _make(*, version: str = "v2", **overrides: Any) -> str:
        return sign(build_claims(version=version, **overrides), rsa_private_key)

    return _make


@pytest.fixture
def auth_settings() -> AppSettings:
    return AppSettings(
        _env_file=None,
        environment="dev",
        auth_enabled=True,
        azure_ad_tenant_id=TENANT_ID,
        azure_ad_client_id=CLIENT_ID,
        azure_ad_client_secret=SecretStr("test-secret"),
        public_base_url=PUBLIC_BASE_URL,
        allowed_hosts=["mcp.test"],
        enabled_toolsets=["diagnostico"],
    )


@pytest.fixture
def dev_settings() -> AppSettings:
    return AppSettings(
        _env_file=None,
        environment="dev",
        auth_enabled=False,
        allowed_hosts=["testserver", "mcp.test"],
        enabled_toolsets=["diagnostico"],
    )
