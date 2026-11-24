"""Acquire canonical Endfield tables from a pinned official Enka commit."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

from skport.assets.manifest import (
    COMMIT_PATTERN,
    MAX_ASSET_BYTES,
    STORE_TABLES,
    AssetSnapshot,
    git_blob_sha,
    parse_json,
    utc_timestamp,
    validate_tables,
)
from skport.errors import AssetError, NetworkError
from skport.transport import RetryPolicy, Transport, retry_after_seconds

OFFICIAL_RAW_BASE = "https://raw.githubusercontent.com/EnkaNetwork/API-docs"
OFFICIAL_API_BASE = "https://api.github.com/repos/EnkaNetwork/API-docs"


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Validated canonical data plus original bytes for durable installation."""

    snapshot: AssetSnapshot
    files: dict[str, bytes]


class EnkaSource:
    """Fetch official store files through the SDK's shared HTTP transport."""

    def __init__(
        self,
        transport: Transport,
        *,
        raw_base: str = OFFICIAL_RAW_BASE,
        api_base: str = OFFICIAL_API_BASE,
        retry: RetryPolicy | None = None,
        concurrency: int = 5,
    ) -> None:
        if concurrency < 1:
            raise AssetError("asset download concurrency must be positive")
        self.transport = transport
        self.raw_base = raw_base.rstrip("/")
        self.api_base = api_base.rstrip("/")
        self.retry = retry or RetryPolicy()
        self._gate = asyncio.Semaphore(concurrency)

    async def _request(self, url: str, *, maximum: int = MAX_ASSET_BYTES) -> bytes:
        """Read a bounded GET response without sending account credentials."""
        for attempt in range(1, self.retry.attempts + 1):
            try:
                async with self._gate:
                    response = await self.transport.request(
                        "GET", url, headers={"Accept": "application/json"}
                    )
            except NetworkError as exc:
                if attempt == self.retry.attempts:
                    raise AssetError(
                        "official Enka asset source is unavailable", path=urlsplit(url).path
                    ) from exc
                await self.retry.sleep(attempt)
                continue
            if response.status == 200:
                payload = response.text.encode("utf-8")
                if len(payload) > maximum:
                    raise AssetError("official asset exceeds the size limit", path=urlsplit(url).path)
                return payload
            if response.status in (408, 425, 429, 500, 502, 503, 504) and attempt < self.retry.attempts:
                delay = retry_after_seconds(
                    response.headers.get("Retry-After") or response.headers.get("retry-after")
                )
                await self.retry.sleep(attempt, delay)
                continue
            raise AssetError(
                "official Enka asset request failed", status=response.status, path=urlsplit(url).path
            )
        raise AssertionError("unreachable asset request state")

    async def resolve(self, ref: str = "master") -> str:
        """Resolve a branch once; a supplied full commit needs no branch lookup."""
        if COMMIT_PATTERN.fullmatch(ref.lower()):
            return ref.lower()
        if not ref.strip():
            raise AssetError("asset source ref must not be empty")
        data = parse_json(await self._request(f"{self.api_base}/commits/{quote(ref, safe='')}"), "commit")
        revision = data.get("sha")
        if not isinstance(revision, str) or not COMMIT_PATTERN.fullmatch(revision):
            raise AssetError("official asset source returned an invalid commit")
        return revision

    async def fetch(self, revision: str, previous_files: dict[str, bytes] | None = None) -> SourceSnapshot:
        """Fetch one commit, verifying each original file against its Git blob."""
        if not COMMIT_PATTERN.fullmatch(revision):
            raise AssetError("canonical assets require a full immutable commit")
        tree = parse_json(
            await self._request(
                f"{self.api_base}/git/trees/{revision}?recursive=1", maximum=16 * 1024 * 1024
            ),
            "source tree",
        )
        if tree.get("truncated") or not isinstance(tree.get("tree"), list):
            raise AssetError("official asset source tree is incomplete")
        entries = {
            item["path"]: item
            for item in tree["tree"]
            if isinstance(item, dict) and item.get("type") == "blob" and isinstance(item.get("path"), str)
        }
        files: dict[str, bytes] = {}
        tables: dict[str, dict[str, Any]] = {}

        async def one(name: str) -> None:
            path = f"store/ef/{name}.json"
            entry = entries.get(path)
            if entry is None or not isinstance(entry.get("sha"), str):
                raise AssetError(f"official source is missing {path}")
            if isinstance(entry.get("size"), int) and entry["size"] > MAX_ASSET_BYTES:
                raise AssetError(f"official source table exceeds size limit: {name}")
            old = (previous_files or {}).get(name)
            payload = (
                old
                if old is not None and git_blob_sha(old) == entry["sha"]
                else (await self._request(f"{self.raw_base}/{revision}/{path}"))
            )
            if git_blob_sha(payload) != entry["sha"]:
                raise AssetError(f"official source blob integrity failed: {name}")
            files[name] = payload
            tables[name] = parse_json(payload, name)

        tasks = [asyncio.create_task(one(name)) for name in STORE_TABLES]
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        validate_tables(tables)
        return SourceSnapshot(AssetSnapshot(revision, tables, utc_timestamp()), files)


def file_hashes(files: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    """Build durable content metadata from exact source bytes."""
    return {
        name: {"sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}
        for name, payload in files.items()
    }
