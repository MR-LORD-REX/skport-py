"""Signed request execution, recovery, and safe request measurements."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode
from uuid import uuid4

from skport.errors import AuthError, DecodeError, PoolExhausted, RateLimitError, SkportError, check_envelope
from skport.metrics import RequestMetric
from skport.transport import game_headers, retry_after_seconds

if TYPE_CHECKING:
    from skport.api.base import RequestAPI
    from skport.auth import PoolUnit
    from skport.config import Language

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def query_pairs(params: Mapping[str, Any] | None) -> list[tuple[str, str]]:
    """Flatten parameters in their supplied order, preserving repeated values."""
    pairs: list[tuple[str, str]] = []
    for key, value in (params or {}).items():
        if value is None:
            continue
        values = value if isinstance(value, (list, tuple)) else (value,)
        pairs.extend((str(key), str(item)) for item in values if item is not None)
    return pairs


def canonical_query(params: Mapping[str, Any] | None) -> str:
    """Encode the exact query sequence used for both signing and transport."""
    return urlencode(query_pairs(params))


async def execute(
    api: RequestAPI,
    method: str,
    path: str,
    params: Mapping[str, Any] | None,
    body: str | None,
    token: str | None,
    role: str | None,
    language: Language,
) -> Any:
    """Lease a credential, recover once, and retry only safe operations."""
    excluded: set[str] = set()
    last_error: SkportError | None = None
    public_attempts = len(api.pool) if token is None else 1
    for _ in range(public_attempts):
        try:
            async with api.pool.lease(token=token, exclude=excluded) as unit:
                try:
                    return await _with_unit(api, unit, method, path, params, body, role, language)
                except (AuthError, RateLimitError) as exc:
                    if token is not None or method not in SAFE_METHODS:
                        raise
                    last_error = exc
                    excluded.add(unit.fingerprint)
                    unit.cooldown(api.config.cooldown)
        except PoolExhausted:
            if last_error is not None:
                raise last_error from None
            raise
    if last_error is not None:
        raise last_error
    raise PoolExhausted("no public credential could serve this request")


async def _with_unit(
    api: RequestAPI,
    unit: PoolUnit,
    method: str,
    path: str,
    params: Mapping[str, Any] | None,
    body: str | None,
    role: str | None,
    language: Language,
) -> Any:
    safe = method in SAFE_METHODS
    attempts = api.retry.attempts if safe else 1
    recovered = False
    attempt = 1
    while True:
        credential = unit.credential
        if credential is None:
            raise AuthError("leased account has no credential")
        generation = credential.generation
        try:
            return await _send(api, unit, method, path, params, body, role, language, attempt)
        except AuthError:
            if not safe or recovered:
                raise
            recovered = True
            await api.pool.renew(unit, generation)
        except SkportError as exc:
            if not safe or not exc.retryable or attempt >= attempts:
                raise
            await api.retry.sleep(attempt, exc.retry_after)
            attempt += 1


async def _send(
    api: RequestAPI,
    unit: PoolUnit,
    method: str,
    path: str,
    params: Mapping[str, Any] | None,
    body: str | None,
    role: str | None,
    language: Language,
    attempt: int,
) -> Any:
    credential = unit.credential
    assert credential is not None
    signed = game_headers(
        language=language,
        protocol=api.config.protocol,
        user_agent=api.config.user_agent,
        cred=credential.cred,
        salt=credential.salt,
        path=path,
        body=canonical_query(params) if method in SAFE_METHODS else (body or ""),
        game_role=role,
    )
    start = asyncio.get_running_loop().time()
    request_id = uuid4().hex[:12]
    status = None
    outcome = "ok"
    try:
        response = await api.transport.request(
            method,
            api.config.hosts.game + path,
            headers=signed.headers,
            params=query_pairs(params),
            body=body,
        )
        status = response.status
        try:
            payload = response.json()
        except DecodeError:
            if response.status < 400:
                raise
            payload = None
        target = bool(params and any(key in params for key in ("uid", "id", "userId")))
        return check_envelope(
            payload,
            status=status,
            path=path,
            method=method,
            target=target,
            retry_after=retry_after_seconds(
                response.headers.get("Retry-After") or response.headers.get("retry-after")
            ),
        )
    except SkportError as exc:
        outcome = type(exc).__name__
        exc.path = path
        exc.attempt = attempt
        exc.context.update(endpoint=path, request_id=request_id, attempt=attempt)
        raise
    finally:
        elapsed = asyncio.get_running_loop().time() - start
        api.metrics.record(RequestMetric(method, path, status, elapsed, False, attempt, unit.fingerprint))
        api.metrics.count(outcome)
