import anyio
import pytest

from utg_mcp.core.cache import KeyedLocks, TtlCache


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_ttl_cache_expires_entries():
    clock = Clock()
    cache: TtlCache[str, int] = TtlCache(max_entries=10, clock=clock)
    cache.set("a", 1, ttl_seconds=10)

    assert cache.get("a") == 1
    clock.now = 10
    assert cache.get("a") is None
    assert len(cache) == 0


def test_ttl_cache_evicts_least_recently_used():
    cache: TtlCache[str, int] = TtlCache(max_entries=2)
    cache.set("a", 1, 60)
    cache.set("b", 2, 60)
    cache.get("a")
    cache.set("c", 3, 60)

    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3


@pytest.mark.anyio
async def test_keyed_locks_serialize_same_key_and_clean_up():
    locks = KeyedLocks()
    active = 0
    max_active = 0

    async def worker() -> None:
        nonlocal active, max_active
        async with locks.hold("k"):
            active += 1
            max_active = max(max_active, active)
            await anyio.sleep(0.01)
            active -= 1

    async with anyio.create_task_group() as tg:
        for _ in range(5):
            tg.start_soon(worker)

    assert max_active == 1
    assert locks._locks == {}
