from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urlsplit

import aiohttp
from yarl import URL

from skport.config import ClientConfig
from skport.errors import ConfigError, DecodeError, NetworkError
from skport.logging import get_logger

_log = get_logger("transport")


@dataclass(slots=True)
class RawResponse:
    """HTTP response needed by centralized envelope and retry handling."""

    status: int
    text: str = field(repr=False)
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)

    def json(self) -> Any:
        """Decode JSON without exposing response bodies in an exception."""
        try:
            return json.loads(self.text)
        except ValueError as exc:
            raise DecodeError("SKPORT returned malformed JSON", status=self.status) from exc


class Transport:
    """Send prepared HTTP requests through one reusable aiohttp session.

    Signing, response classification, and retries belong to the API pipeline.
    An externally supplied session remains owned by its caller.
    """

    def __init__(self, config: ClientConfig, session: aiohttp.ClientSession | None = None) -> None:
        self._config = config
        self._session = session
        self._owns_session = session is None
        self._closed = False
        self._close_lock = asyncio.Lock()

    @property
    def session(self) -> aiohttp.ClientSession:
        """Return the session, creating an owned one on first request."""
        if self._closed:
            raise ConfigError("transport is closed")
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._config.timeout),
                headers={"User-Agent": self._config.user_agent},
            )
        if self._session.closed:
            raise ConfigError("HTTP session is closed")
        return self._session

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | Sequence[tuple[str, str]] | None = None,
        body: str | None = None,
    ) -> RawResponse:
        """Send once, preserving the encoded URL used by the signer.

        Ordered query pairs preserve duplicate keys. Redirects are returned to
        the pipeline rather than forwarding credential headers to another URL.
        """
        if params:
            query = urlencode(params, doseq=True)
            url = f"{url}{'&' if '?' in url else '?'}{query}"
        endpoint = urlsplit(url).path
        started = asyncio.get_running_loop().time()
        status = None
        try:
            async with self.session.request(
                method.upper(),
                URL(url, encoded=True),
                headers=headers,
                data=body,
                timeout=aiohttp.ClientTimeout(total=self._config.timeout),
                allow_redirects=False,
            ) as response:
                status = response.status
                return RawResponse(response.status, await response.text(), dict(response.headers))
        except (TimeoutError, aiohttp.ClientError) as exc:
            raise NetworkError("HTTP request did not complete", path=endpoint) from exc
        finally:
            elapsed = asyncio.get_running_loop().time() - started
            _log.debug("%s %s status=%s duration_ms=%.0f", method.upper(), endpoint, status, elapsed * 1000)

    async def close(self) -> None:
        """Close an owned session once, leaving external sessions open."""
        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
            if self._owns_session and self._session is not None:
                await self._session.close()
            self._session = None
