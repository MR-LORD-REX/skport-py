"""Bounded asynchronous caching with independent producer lifetimes."""

from __future__ import annotations

import asyncio
import copy
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
from typing import Any, TypeVar

T = TypeVar("T")


class TTLCache:
    """Protect shared fetches from waiter cancellation and stale invalidation."""

    def __init__(self, max_entries: int = 512) -> None:
        self._values: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._running: dict[Hashable, asyncio.Task[Any]] = {}
        self._invalidated: set[asyncio.Task[Any]] = set()
        self._max_entries = max_entries

    async def get(
        self,
        key: Hashable,
        ttl: float,
        fetch: Callable[[], Awaitable[T]],
        *,
        keep: Callable[[T], bool] = lambda _: True,
    ) -> T:
        """Return a defensive copy, coalescing simultaneous misses."""
        now = time.monotonic()
        hit = self._values.get(key)
        if hit is not None:
            if hit[0] > now:
                self._values.move_to_end(key)
                return copy.deepcopy(hit[1])
            self._values.pop(key, None)
        running = self._running.get(key)
        if running is None:
            running = asyncio.create_task(self._produce(key, ttl, fetch, keep))
            self._running[key] = running
            running.add_done_callback(self._observe_failure)
        return copy.deepcopy(await asyncio.shield(running))

    async def _produce(
        self,
        key: Hashable,
        ttl: float,
        fetch: Callable[[], Awaitable[T]],
        keep: Callable[[T], bool],
    ) -> T:
        task = asyncio.current_task()
        try:
            value = await fetch()
            if task not in self._invalidated and ttl > 0 and keep(value):
                now = time.monotonic()
                for expired in [key for key, (until, _) in self._values.items() if until <= now]:
                    self._values.pop(expired, None)
                self._values[key] = (now + ttl, copy.deepcopy(value))
                self._values.move_to_end(key)
                while len(self._values) > self._max_entries:
                    self._values.popitem(last=False)
            return value
        finally:
            if self._running.get(key) is task:
                self._running.pop(key, None)
            if task is not None:
                self._invalidated.discard(task)

    @staticmethod
    def _observe_failure(task: asyncio.Task[Any]) -> None:
        if not task.cancelled():
            task.exception()

    def drop(self, match: Callable[[Hashable], bool] = lambda _: True) -> None:
        """Invalidate values and fence matching producers already in progress."""
        for key in list(self._values):
            if match(key):
                self._values.pop(key, None)
        for key, task in list(self._running.items()):
            if match(key):
                self._invalidated.add(task)
                self._running.pop(key, None)

    def clear(self) -> None:
        """Invalidate every value and running producer."""
        self.drop()

    async def close(self) -> None:
        """Cancel and await unfinished producers before transport shutdown."""
        tasks = set(self._running.values()) | self._invalidated
        self.clear()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._invalidated.clear()

    def __len__(self) -> int:
        return len(self._values)
