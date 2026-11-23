from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from skport.auth.credential import Credential
from skport.auth.flow import AuthFlow
from skport.auth.store import CredentialStore
from skport.config import ClientConfig
from skport.errors import AuthError, ConfigError, PoolExhausted, SkportError
from skport.logging import fingerprint, get_logger

_log = get_logger("pool")


@dataclass(slots=True)
class PoolUnit:
    """One account's credential, concurrency gate, and health state."""

    token: str = field(repr=False)
    concurrency: int = 1
    credential: Credential | None = field(default=None, repr=False)
    gate: asyncio.Semaphore = field(init=False, repr=False)
    auth_lock: asyncio.Lock = field(init=False, repr=False)
    failures: int = 0
    cooldown_until: float = 0.0
    last_used: float = 0.0
    last_error: str | None = None

    def __post_init__(self) -> None:
        self.gate = asyncio.Semaphore(self.concurrency)
        self.auth_lock = asyncio.Lock()

    @property
    def fingerprint(self) -> str:
        """Non-secret identifier suitable for logs and request exclusions."""
        return fingerprint(self.token)

    @property
    def ready(self) -> bool:
        """Whether this account can be selected after its cooldown."""
        return time.monotonic() >= self.cooldown_until

    def cooldown(self, seconds: float) -> None:
        """Temporarily remove an account from public rotation."""
        self.failures += 1
        self.cooldown_until = time.monotonic() + max(0.0, seconds)


class TokenPool:
    """Reuse credentials fairly, with an outbound gate for each account.

    Explicit owner tokens outside the public pool receive separate retained
    units. They are never selected to inspect another user's public profile.
    """

    def __init__(
        self,
        tokens: list[str],
        config: ClientConfig,
        flow: AuthFlow,
        store: CredentialStore | None = None,
    ) -> None:
        normalized = list(dict.fromkeys(self._token(token) for token in tokens))
        if not normalized:
            raise ConfigError("at least one public account token is required")
        self.config = config
        self.flow = flow
        self.store = store
        if self.store is None and config.login_store is not None:
            self.store = CredentialStore(config.login_store, namespace=config.region.value)
        self.units = [PoolUnit(token, config.per_token_concurrency) for token in normalized]
        self._by_token = {unit.token: unit for unit in self.units}
        self._order = deque(self.units)
        self._index_lock = asyncio.Lock()
        self._close_lock = asyncio.Lock()
        self._closing = self._closed = False

    @staticmethod
    def _token(token: str) -> str:
        if not isinstance(token, str) or not token.strip():
            raise ConfigError("account tokens must be nonempty strings")
        return token.strip()

    def _assert_open(self) -> None:
        if self._closing or self._closed:
            raise ConfigError("token pool is closed")

    def __len__(self) -> int:
        return len(self.units)

    @property
    def warm(self) -> bool:
        """Whether all public accounts have credentials and are eligible."""
        return bool(self.units) and all(unit.credential is not None and unit.ready for unit in self.units)

    def unit_for(self, token: str) -> PoolUnit:
        """Find or retain an explicit owner unit without adding it to rotation."""
        self._assert_open()
        normalized = self._token(token)
        if normalized not in self._by_token:
            self._by_token[normalized] = PoolUnit(normalized, self.config.per_token_concurrency)
        return self._by_token[normalized]

    async def warm_all(self) -> list[PoolUnit]:
        """Warm public accounts concurrently, tolerating individual failures."""
        self._assert_open()
        units = tuple(self.units)
        results = await asyncio.gather(*(self._warm_one(unit) for unit in units), return_exceptions=True)
        healthy: list[PoolUnit] = []
        for unit, result in zip(units, results, strict=True):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, SkportError):
                _log.warning("account %s could not warm: %s", unit.fingerprint, type(result).__name__)
            elif isinstance(result, BaseException):
                raise result
            else:
                healthy.append(unit)
        if not healthy:
            raise self._exhausted()
        return healthy

    async def _warm_one(self, unit: PoolUnit) -> None:
        async with unit.gate:
            self._assert_open()
            if not unit.ready:
                raise self._exhausted()
            try:
                await self._ready(unit)
            except SkportError as exc:
                self._failed(unit, exc)
                raise
            finally:
                unit.last_used = time.monotonic()

    async def credential_for(self, token: str) -> Credential:
        """Return an owner's credential after serialized authentication."""
        async with self.lease(token=token) as unit:
            assert unit.credential is not None
            return unit.credential

    async def _prepare(self, unit: PoolUnit) -> Credential:
        if unit.credential is not None:
            return unit.credential
        async with unit.auth_lock:
            if unit.credential is None:
                self._check_available(unit)
                stored = self.store.load(unit.token) if self.store else None
                unit.credential = stored or await self.flow.authenticate(unit.token)
                if stored is None:
                    self._save(unit)
                unit.failures = 0
                unit.cooldown_until = 0.0
                unit.last_error = None
            return unit.credential

    def _save(self, unit: PoolUnit) -> None:
        if self.store is not None and unit.credential is not None:
            self.store.save(unit.credential)

    @staticmethod
    def _check_available(unit: PoolUnit) -> None:
        if not unit.ready:
            raise PoolExhausted(
                "selected account is cooling down",
                retry_after=max(0.0, unit.cooldown_until - time.monotonic()),
                context={"account": unit.fingerprint},
            )

    def _failed(self, unit: PoolUnit, error: SkportError) -> None:
        if unit.ready:
            unit.last_error = type(error).__name__
            unit.cooldown(self.config.cooldown)
        unit.last_used = time.monotonic()

    async def _ready(self, unit: PoolUnit) -> None:
        self._assert_open()
        self._check_available(unit)
        remaining = self.config.min_interval - (time.monotonic() - unit.last_used)
        if remaining > 0:
            await asyncio.sleep(remaining)
        credential = await self._prepare(unit)
        if credential.refresh_due(self.config.refresh_interval):
            await self.renew(unit, credential.generation)

    async def renew(self, unit: PoolUnit, generation: int) -> Credential:
        """Renew under the auth lock while the caller holds the outbound gate.

        A changed generation means another caller already renewed this account.
        Refresh rejection triggers a full exchange for the same account only.
        Network or server failures propagate without discarding credentials.
        """
        async with unit.auth_lock:
            credential = unit.credential
            if credential is None:
                raise AuthError("account has no credential to renew")
            if credential.generation != generation:
                return credential
            try:
                await self.flow.refresh(credential)
            except AuthError:
                replacement = await self.flow.authenticate(unit.token)
                replacement.generation = credential.generation + 1
                credential.clear()
                unit.credential = replacement
            self._save(unit)
            unit.failures = 0
            unit.cooldown_until = 0.0
            unit.last_error = None
            assert unit.credential is not None
            return unit.credential

    @asynccontextmanager
    async def lease(
        self,
        *,
        token: str | None = None,
        exclude: set[str] | None = None,
    ) -> AsyncIterator[PoolUnit]:
        """Hold one account's gate through authentication and request completion.

        Public selection skips unavailable accounts and failed cold logins.
        Explicit owner calls keep their account identity on every failure.
        """
        self._assert_open()
        if token is not None:
            unit = self.unit_for(token)
            async with unit.gate:
                try:
                    try:
                        await self._ready(unit)
                    except SkportError as exc:
                        self._failed(unit, exc)
                        raise
                    yield unit
                finally:
                    unit.last_used = time.monotonic()
            return
        excluded = set(exclude or ())
        while True:
            unit = await self._pick(excluded)
            async with unit.gate:
                self._assert_open()
                if not unit.ready:
                    excluded.add(unit.fingerprint)
                    continue
                try:
                    await self._ready(unit)
                except SkportError as exc:
                    self._failed(unit, exc)
                    excluded.add(unit.fingerprint)
                    continue
                failures = unit.failures
                try:
                    yield unit
                    if unit.failures == failures:
                        unit.failures = 0
                        unit.cooldown_until = 0.0
                        unit.last_error = None
                finally:
                    unit.last_used = time.monotonic()
                return

    async def _pick(self, excluded: set[str]) -> PoolUnit:
        async with self._index_lock:
            self._assert_open()
            candidates = [
                (index, unit)
                for index, unit in enumerate(self._order)
                if unit.ready and unit.fingerprint not in excluded and unit.token not in excluded
            ]
            if not candidates:
                raise self._exhausted()
            available = [(index, unit) for index, unit in candidates if not unit.gate.locked()]
            index, unit = (available or candidates)[0]
            self._order.rotate(-(index + 1))
            return unit

    def _exhausted(self) -> PoolExhausted:
        return PoolExhausted(
            "no public account is available",
            context={
                "accounts": {
                    unit.fingerprint: {"failures": unit.failures, "error": unit.last_error}
                    for unit in self.units
                }
            },
        )

    async def close(self) -> None:
        """Wait for account gates, then release retained credential references."""
        async with self._close_lock:
            if self._closed:
                return
            self._closing = True
            for unit in list(self._by_token.values()):
                acquired = 0
                try:
                    for _ in range(unit.concurrency):
                        await unit.gate.acquire()
                        acquired += 1
                    if unit.credential is not None:
                        unit.credential.clear()
                    unit.credential = None
                    unit.token = ""
                finally:
                    for _ in range(acquired):
                        unit.gate.release()
            self._by_token.clear()
            self._order.clear()
            self.units.clear()
            self._closed = True
