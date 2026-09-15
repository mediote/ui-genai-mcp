import threading
import time
from typing import Any

import anyio
import pytest

from utg_mcp.auth.obo import OboTokenProvider
from utg_mcp.core.errors import AuthenticationRequired, ConfigurationError, UpstreamUnavailable

pytestmark = pytest.mark.anyio

GRAPH = ["https://graph.microsoft.com/.default"]


class FakeMsal:
    def __init__(self, result: dict[str, Any] | None = None, delay: float = 0.0) -> None:
        self.result = result or {"access_token": "graph-token", "expires_in": 3600}
        self.delay = delay
        self.calls = 0
        self._lock = threading.Lock()

    def acquire_token_on_behalf_of(self, user_assertion: str, scopes: list[str]) -> dict[str, Any]:
        with self._lock:
            self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return self.result


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _provider(fake: FakeMsal, clock: FakeClock | None = None) -> OboTokenProvider:
    return OboTokenProvider(client_factory=lambda: fake, clock=clock or FakeClock())


async def test_exchanges_and_caches_token():
    fake = FakeMsal()
    provider = _provider(fake)

    assert await provider.get_token("user-assertion", GRAPH) == "graph-token"
    assert await provider.get_token("user-assertion", GRAPH) == "graph-token"
    assert fake.calls == 1


async def test_cache_is_keyed_by_assertion_and_scopes():
    fake = FakeMsal()
    provider = _provider(fake)

    await provider.get_token("user-a", GRAPH)
    await provider.get_token("user-b", GRAPH)
    await provider.get_token("user-a", ["https://storage.azure.com/.default"])

    assert fake.calls == 3


async def test_concurrent_requests_share_a_single_exchange():
    fake = FakeMsal(delay=0.05)
    provider = _provider(fake)

    async with anyio.create_task_group() as tg:
        for _ in range(10):
            tg.start_soon(provider.get_token, "user-assertion", GRAPH)

    assert fake.calls == 1


async def test_token_is_refreshed_before_expiry():
    fake = FakeMsal({"access_token": "t", "expires_in": 3600})
    clock = FakeClock()
    provider = _provider(fake, clock)

    await provider.get_token("user-assertion", GRAPH)
    clock.now += 3600 - 300 + 1  # passou da margem de 5 min
    await provider.get_token("user-assertion", GRAPH)

    assert fake.calls == 2


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("invalid_grant", AuthenticationRequired),
        ("interaction_required", AuthenticationRequired),
        ("invalid_client", ConfigurationError),
        ("temporarily_unavailable", UpstreamUnavailable),
    ],
)
async def test_maps_msal_errors(error, expected):
    fake = FakeMsal({"error": error, "error_description": "AADSTS: user@example.com detalhes"})

    with pytest.raises(expected):
        await _provider(fake).get_token("user-assertion", GRAPH)


async def test_failed_exchange_is_not_cached():
    fake = FakeMsal({"error": "temporarily_unavailable"})
    provider = _provider(fake)

    for _ in range(2):
        with pytest.raises(UpstreamUnavailable):
            await provider.get_token("user-assertion", GRAPH)

    assert fake.calls == 2


async def test_client_construction_failure_is_upstream_unavailable():
    def broken_factory() -> Any:
        raise OSError("authority discovery failed")

    provider = OboTokenProvider(client_factory=broken_factory)

    with pytest.raises(UpstreamUnavailable):
        await provider.get_token("user-assertion", GRAPH)
