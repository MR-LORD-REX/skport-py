"""Shared API lifecycle, caching, and transport entry points."""

from __future__ import annotations

import asyncio
import copy
import math
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Any, Self
from urllib.parse import urlsplit

from skport.api import endpoints as ep
from skport.api.request import SAFE_METHODS, execute, query_pairs
from skport.auth import AuthFlow, TokenPool
from skport.cache import TTLCache
from skport.config import ClientConfig, Language, parse_language
from skport.errors import ConfigError, DecodeError, SkportError, check_envelope
from skport.logging import fingerprint
from skport.metrics import Metrics
from skport.transport import RetryPolicy, Transport, compact_json, plain_headers, retry_after_seconds


@dataclass(slots=True)
class _Lifecycle:
    closed: bool = False
    closing: bool = False
    active: dict[asyncio.Task[Any], asyncio.Future[None]] = field(default_factory=dict)


class RequestAPI:
    """Own request infrastructure; game and social helpers extend this class."""

    owner_paths: frozenset[str] = frozenset()

    def __init__(
        self,
        tokens: Sequence[str] | None = None,
        *,
        pool: TokenPool | None = None,
        config: ClientConfig | None = None,
        transport: Transport | None = None,
        cache: TTLCache | bool | None = None,
        metrics: Metrics | None = None,
        retry: RetryPolicy | None = None,
        lang: str | Language | None = None,
        **settings: Any,
    ) -> None:
        if isinstance(tokens, (str, bytes)):
            raise ConfigError("tokens must be a sequence of account tokens")
        if tokens is not None and pool is not None:
            raise ConfigError("provide tokens or a prepared pool, not both")
        base = config or (pool.config if pool is not None else ClientConfig())
        if lang is not None:
            settings["lang"] = parse_language(lang)
        self.config = replace(base, **settings)
        self.transport = transport or (pool.flow.transport if pool is not None else Transport(self.config))
        self._owns_transport = transport is None and pool is None
        self.pool = (
            pool
            if pool is not None
            else TokenPool(list(tokens or []), self.config, AuthFlow(self.config, self.transport))
        )
        self._owns_pool = pool is None
        self.cache = (
            cache
            if isinstance(cache, TTLCache)
            else (
                TTLCache(self.config.cache_size) if (self.config.cache if cache is None else cache) else None
            )
        )
        self.metrics = metrics if metrics is not None else Metrics()
        self.retry = retry or RetryPolicy(
            attempts=self.config.max_attempts, backoff=self.config.retry_backoff
        )
        self._state = _Lifecycle()
        self._view = False
        self._close_lock = asyncio.Lock()
        self._credential_cache: dict[tuple[str, str, str], tuple[float, str]] = {}

    async def __aenter__(self) -> Self:
        self._assert_open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    def _assert_open(self) -> None:
        task = asyncio.current_task()
        if self._state.closed or (self._state.closing and task not in self._state.active):
            raise ConfigError("API is closed")

    @contextmanager
    def _operation(self) -> Iterator[None]:
        self._assert_open()
        task = asyncio.current_task()
        owned = task is not None and task not in self._state.active
        if owned and task is not None:
            self._state.active[task] = asyncio.get_running_loop().create_future()
        try:
            yield
        finally:
            if owned and task is not None:
                completion = self._state.active.pop(task)
                if not completion.done():
                    completion.set_result(None)

    def with_language(self, lang: str | Language) -> Self:
        """Return a borrowing locale view over the same pool, session and cache."""
        if self._state.closed or self._state.closing:
            raise ConfigError("API is closed")
        view = copy.copy(self)
        view.config = replace(self.config, lang=parse_language(lang))
        view._view = True
        return view

    async def warm(self) -> None:
        """Authenticate public pool units concurrently before serving reads."""
        with self._operation():
            await self.pool.warm_all()

    async def refresh(self, *, token: str) -> None:
        """Refresh one explicitly selected account under its request lease."""
        with self._operation():
            async with self.pool.lease(token=token) as unit:
                assert unit.credential is not None
                await self.pool.renew(unit, unit.credential.generation)

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        payload: Mapping[str, Any] | None = None,
        token: str | None = None,
        role: str | None = None,
        lang: str | Language | None = None,
        ttl: float | None = None,
        cache: bool = True,
    ) -> Any:
        """Execute a signed game request and return its raw data field.

        Public requests can use any pool unit. Owner requests must provide token.
        Writes never retry automatically, including uncertain timeout outcomes.
        """
        with self._operation():
            method = method.upper()
            if not path.startswith("/") or "?" in path or "#" in path or path.startswith("//"):
                raise ConfigError("path must be an absolute endpoint path without a query")
            if method not in SAFE_METHODS and token is None:
                raise ConfigError("write requests require an explicit account token")
            if path in self.owner_paths and token is None:
                raise ConfigError("this endpoint requires an explicit owner token")
            if role and token is None:
                raise ConfigError("owner role headers require an explicit account token")
            if path in (ep.CARDS, ep.BINDING, ep.PROFILE, ep.WEB_PROFILE) and token is None:
                identity = (params or {}).get("uid", (params or {}).get("id"))
                if identity is None or isinstance(identity, bool) or not str(identity).strip():
                    raise ConfigError("owner lookups require an explicit account token")
            language = parse_language(lang if lang is not None else self.config.lang)
            body = compact_json(payload) if payload is not None else None
            seconds = 60.0 if ttl is None else ttl
            if not math.isfinite(seconds) or seconds < 0:
                raise ConfigError("ttl must be finite and nonnegative")
            scope = fingerprint(token.strip()) if token is not None else "public"
            key = (
                self.config.hosts.game,
                language.value,
                method,
                path,
                tuple(query_pairs(params)),
                role,
                scope,
            )

            async def fetch() -> Any:
                return await execute(self, method, path, params, body, token, role, language)

            if method == "GET" and cache and seconds > 0 and self.cache is not None:
                result = await self.cache.get(key, seconds, fetch)
            else:
                result = await fetch()
            if method not in SAFE_METHODS and self.cache is not None:
                self.cache.drop(lambda key: isinstance(key, tuple) and key[-1] == scope)
            return result

    async def external_request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        payload: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        lang: str | Language | None = None,
        envelope: bool = True,
    ) -> Any:
        """Use the same transport for unsigned OAuth, binding, records and news.

        Account helpers hold an owner lease around this call. This method does
        not acquire another lease, preventing nested account-gate deadlocks.
        """
        with self._operation():
            method = method.upper()
            language = parse_language(lang if lang is not None else self.config.lang)
            merged = {
                **plain_headers(user_agent=self.config.user_agent),
                "sk-language": language.value,
                "x-language": language.value,
                **dict(headers or {}),
            }
            body = compact_json(payload) if payload is not None else None
            attempts = self.retry.attempts if method in SAFE_METHODS else 1
            for attempt in range(1, attempts + 1):
                try:
                    response = await self.transport.request(
                        method, url, params=query_pairs(params), body=body, headers=merged
                    )
                    try:
                        data = response.json()
                    except DecodeError:
                        if response.status < 400:
                            raise
                        data = None
                    if not envelope and response.status == 200:
                        return data
                    return check_envelope(
                        data,
                        status=response.status,
                        path=urlsplit(url).path,
                        method=method,
                        retry_after=retry_after_seconds(response.headers.get("Retry-After")),
                    )
                except SkportError as exc:
                    exc.attempt = attempt
                    if method not in SAFE_METHODS or not exc.retryable or attempt == attempts:
                        raise
                    await self.retry.sleep(attempt, exc.retry_after)
            raise AssertionError("unreachable request state")

    async def close(self) -> None:
        """Drain operations and close only resources owned by this API."""
        if self._view:
            return
        async with self._close_lock:
            if self._state.closed:
                return
            self._state.closing = True
            if self.cache is not None:
                await self.cache.close()
            task = asyncio.current_task()
            active = [done for item, done in self._state.active.items() if item is not task]
            if active:
                await asyncio.gather(*(asyncio.shield(done) for done in active), return_exceptions=True)
            if self._owns_pool:
                await self.pool.close()
            self._credential_cache.clear()
            if self._owns_transport:
                await self.transport.close()
            self._state.closed = True
