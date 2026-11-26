"""Regression tests for cache cancellation, isolation and invalidation."""

import asyncio

import pytest

from skport.cache import TTLCache


async def test_first_waiter_cancellation_does_not_cancel_other_waiters():
    cache = TTLCache()
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"items": [1]}

    first = asyncio.create_task(cache.get("key", 60, fetch))
    await started.wait()
    follower = asyncio.create_task(cache.get("key", 60, fetch))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    assert await follower == {"items": [1]}
    assert calls == 1
    assert await cache.get("key", 60, fetch) == {"items": [1]}
    await cache.close()


async def test_invalidated_producer_cannot_replace_fresh_result():
    cache = TTLCache()
    started = asyncio.Event()
    release = asyncio.Event()

    async def stale():
        started.set()
        await release.wait()
        return {"version": 1}

    async def fresh():
        return {"version": 2}

    old = asyncio.create_task(cache.get("key", 60, stale))
    await started.wait()
    cache.drop(lambda key: key == "key")
    assert await cache.get("key", 60, fresh) == {"version": 2}
    release.set()
    assert await old == {"version": 1}
    assert await cache.get("key", 60, stale) == {"version": 2}
    await cache.close()


async def test_defensive_copy_expiry_and_bound(monkeypatch):
    cache = TTLCache(max_entries=2)
    clock = [10.0]
    monkeypatch.setattr("skport.cache.time.monotonic", lambda: clock[0])
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        return {"items": [calls]}

    first = await cache.get("a", 1, fetch)
    first["items"].append(99)
    assert await cache.get("a", 1, fetch) == {"items": [1]}
    clock[0] = 12.0
    assert await cache.get("a", 1, fetch) == {"items": [2]}
    await cache.get("b", 1, fetch)
    await cache.get("c", 1, fetch)
    assert len(cache) == 2
    await cache.close()


async def test_errors_are_not_cached_and_close_cancels_producers():
    cache = TTLCache()
    calls = 0

    async def broken():
        nonlocal calls
        calls += 1
        raise ValueError("fixture failure")

    for _ in range(2):
        with pytest.raises(ValueError):
            await cache.get("key", 60, broken)
    assert calls == 2
    waiting = asyncio.Event()

    async def blocked():
        waiting.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(cache.get("pending", 60, blocked))
    await waiting.wait()
    await cache.close()
    with pytest.raises(asyncio.CancelledError):
        await task
