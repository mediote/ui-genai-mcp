"""Primitivas de cache em memória: TTL com limite de tamanho e locks por chave (single-flight)."""

import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import anyio


class TtlCache[K, V]:
    """Cache TTL + LRU simples.

    Em memória do processo: adequado a 1 worker por réplica (não compartilha entre processos).
    """

    def __init__(self, *, max_entries: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._data: OrderedDict[K, tuple[V, float]] = OrderedDict()
        self._max_entries = max_entries
        self._clock = clock

    def get(self, key: K) -> V | None:
        item = self._data.get(key)
        if item is None:
            return None
        value, expires_at = item
        if self._clock() >= expires_at:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: K, value: V, ttl_seconds: float) -> None:
        self._data[key] = (value, self._clock() + ttl_seconds)
        self._data.move_to_end(key)
        while len(self._data) > self._max_entries:
            self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)


class KeyedLocks:
    """Um `anyio.Lock` por chave, removido quando ninguém mais o usa."""

    def __init__(self) -> None:
        self._locks: dict[str, tuple[anyio.Lock, int]] = {}

    @asynccontextmanager
    async def hold(self, key: str) -> AsyncIterator[None]:
        lock, users = self._locks.get(key, (anyio.Lock(), 0))
        self._locks[key] = (lock, users + 1)
        try:
            async with lock:
                yield
        finally:
            lock, users = self._locks[key]
            if users <= 1:
                del self._locks[key]
            else:
                self._locks[key] = (lock, users - 1)
