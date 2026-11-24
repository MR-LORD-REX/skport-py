"""Atomic user-cache snapshots with online refresh and offline recovery."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from skport.assets.manifest import (
    COMMIT_PATTERN,
    MAX_ASSET_BYTES,
    STORE_TABLES,
    AssetSnapshot,
    AssetUpdate,
    parse_json,
    validate_tables,
)
from skport.assets.source import EnkaSource, SourceSnapshot, file_hashes
from skport.config import ClientConfig
from skport.errors import AssetError
from skport.logging import get_logger
from skport.transport import RetryPolicy, Transport

_log = get_logger("assets")
_DIRECTORY_PATTERN = re.compile(r"^[0-9a-f]{40}-[0-9a-f]{8}$")


def default_asset_path() -> Path:
    """Choose a user-writable cache without touching the installed package."""
    cwd=Path.cwd()
    assets_path= cwd / ".sk_assets"
    os.makedirs(assets_path,exist_ok=True)
    return assets_path

class AssetManager:
    """Share one coherent asset snapshot across games and locale views."""

    def __init__(
        self,
        config: ClientConfig,
        transport: Transport,
        cache_dir: Path | None = None,
        *,
        source: EnkaSource | None = None,
    ) -> None:
        self.config = config
        self.transport = transport
        configured = getattr(config, "assets_dir", None)
        self.path = Path(cache_dir or configured or default_asset_path()).expanduser()
        self.source = source or EnkaSource(
            transport, retry=RetryPolicy(attempts=config.max_attempts, backoff=config.retry_backoff)
        )
        self._current: AssetSnapshot | None = None
        self._files: dict[str, bytes] = {}
        self._lock = asyncio.Lock()
        self._ensure_task: asyncio.Task[AssetSnapshot] | None = None
        self._update_task: asyncio.Task[AssetUpdate] | None = None
        self._closed = False
        self._close_task: asyncio.Task[None] | None = None

    @property
    def current(self) -> AssetSnapshot | None:
        """The already loaded snapshot, without performing implicit I/O."""
        return self._current

    def _assert_open(self) -> None:
        if self._closed:
            raise AssetError("asset manager is closed")

    async def ensure(self) -> AssetSnapshot:
        """Load once, coalescing callers and surviving failed refresh with a cache."""
        self._assert_open()
        if self._current is not None:
            return self._current
        if self._ensure_task is None or self._ensure_task.done():
            self._ensure_task = asyncio.create_task(self._ensure())
            self._ensure_task.add_done_callback(self._observe_failure)
        return await asyncio.shield(self._ensure_task)

    async def _ensure(self) -> AssetSnapshot:
        async with self._lock:
            if self._current is None:
                await self._read_cache()
        offline = getattr(self.config, "assets_offline", False)
        if offline:
            if self._current is None:
                raise AssetError("no valid canonical snapshot is available offline")
            return self._current
        if self._current is not None and not getattr(self.config, "assets_auto_update", True):
            return self._current
        try:
            return (await self.update()).snapshot
        except AssetError:
            if self._current is None:
                raise
            _log.warning("asset refresh failed; retaining revision %s", self._current.revision)
            return self._current

    async def update(self) -> AssetUpdate:
        """Install the newest verified snapshot; preserve the prior one on failure."""
        self._assert_open()
        if getattr(self.config, "assets_offline", False):
            raise AssetError("asset updates are disabled in offline mode")
        if self._update_task is None or self._update_task.done():
            self._update_task = asyncio.create_task(self._update())
            self._update_task.add_done_callback(self._observe_failure)
        return await asyncio.shield(self._update_task)

    async def _update(self) -> AssetUpdate:
        async with self._lock:
            if self._current is None:
                await self._read_cache()
            previous = self._current.revision if self._current is not None else None
            revision = await self.source.resolve(getattr(self.config, "assets_ref", "master"))
            if previous == revision:
                assert self._current is not None
                return AssetUpdate(self._current, False, previous)
            acquired = await self.source.fetch(revision, self._files)
            await self._commit(acquired)
            self._files = acquired.files
            self._current = acquired.snapshot
            return AssetUpdate(acquired.snapshot, True, previous)

    async def _commit(self, acquired: SourceSnapshot) -> None:
        """Finish an atomic disk install even if shutdown cancels the producer."""
        task = asyncio.create_task(asyncio.to_thread(self._install, acquired))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def _read_cache(self) -> None:
        try:
            loaded = await asyncio.to_thread(self._load)
        except AssetError:
            _log.warning("cached canonical snapshot is invalid; a fresh download is required")
            return
        if loaded is not None:
            self._current, self._files = loaded

    def _load(self) -> tuple[AssetSnapshot, dict[str, bytes]] | None:
        pointer = self.path / "current.json"
        if not pointer.exists():
            return None
        try:
            index = parse_json(pointer.read_bytes(), "snapshot pointer")
            directory = index.get("directory")
            if (
                index.get("version") != 1
                or not isinstance(directory, str)
                or not _DIRECTORY_PATTERN.fullmatch(directory)
            ):
                raise AssetError("cached snapshot pointer is invalid")
            folder = self.path / "snapshots" / directory
            manifest = parse_json((folder / "manifest.json").read_bytes(), "snapshot manifest")
            revision, fetched_at = manifest.get("revision"), manifest.get("fetched_at")
            if not isinstance(revision, str) or not COMMIT_PATTERN.fullmatch(revision):
                raise AssetError("cached snapshot commit is invalid")
            if not directory.startswith(revision + "-") or not isinstance(fetched_at, str):
                raise AssetError("cached snapshot provenance is inconsistent")
            hashes = manifest.get("files")
            if not isinstance(hashes, dict) or set(hashes) != set(STORE_TABLES):
                raise AssetError("cached snapshot file manifest is incomplete")
            files: dict[str, bytes] = {}
            tables: dict[str, dict[str, Any]] = {}
            for name in STORE_TABLES:
                file = folder / f"{name}.json"
                if file.stat().st_size > MAX_ASSET_BYTES:
                    raise AssetError(f"cached snapshot exceeds size limit: {name}")
                payload = file.read_bytes()
                metadata = hashes[name]
                if not isinstance(metadata, dict) or metadata.get("size") != len(payload):
                    raise AssetError(f"cached snapshot size mismatch: {name}")
                if metadata.get("sha256") != hashlib.sha256(payload).hexdigest():
                    raise AssetError(f"cached snapshot integrity failed: {name}")
                files[name] = payload
                tables[name] = parse_json(payload, name)
            validate_tables(tables)
            return AssetSnapshot(revision, tables, fetched_at), files
        except OSError as exc:
            raise AssetError("cached snapshot cannot be read") from exc

    @staticmethod
    def _write(path: Path, payload: bytes) -> None:
        with path.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

    def _install(self, acquired: SourceSnapshot) -> None:
        root = self.path.resolve()
        staging: Path | None = None
        temporary: Path | None = None
        try:
            root.mkdir(parents=True, exist_ok=True)
            snapshots = root / "snapshots"
            snapshots.mkdir(exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix=".stage-", dir=root))
            for name, payload in acquired.files.items():
                self._write(staging / f"{name}.json", payload)
            manifest = {
                "version": 1,
                "revision": acquired.snapshot.revision,
                "fetched_at": acquired.snapshot.fetched_at,
                "files": file_hashes(acquired.files),
            }
            self._write(staging / "manifest.json", json.dumps(manifest, separators=(",", ":")).encode())
            directory = f"{acquired.snapshot.revision}-{uuid4().hex[:8]}"
            staging.rename(snapshots / directory)
            staging = None
            temporary = root / f".current-{uuid4().hex}.tmp"
            self._write(temporary, json.dumps({"version": 1, "directory": directory}).encode())
            os.replace(temporary, root / "current.json")
            temporary = None
        except OSError as exc:
            raise AssetError("canonical snapshot could not be installed") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            if staging is not None and staging.exists():
                resolved = staging.resolve()
                if resolved.is_relative_to(root) and resolved.name.startswith(".stage-"):
                    shutil.rmtree(resolved)

    @staticmethod
    def _observe_failure(task: asyncio.Task[Any]) -> None:
        if not task.cancelled():
            task.exception()

    async def close(self) -> None:
        """Cancel unfinished asset producers before shared transport shutdown."""
        if self._close_task is None:
            self._closed = True
            self._close_task = asyncio.create_task(self._drain())
            self._close_task.add_done_callback(self._observe_failure)
        await asyncio.shield(self._close_task)

    async def _drain(self) -> None:
        """Drain producers, including an atomic disk commit already in progress."""
        tasks = [
            task for task in (self._ensure_task, self._update_task) if task is not None and not task.done()
        ]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
