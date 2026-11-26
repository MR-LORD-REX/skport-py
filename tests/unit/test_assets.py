"""Official-source and atomic-cache contracts without external network access."""

from __future__ import annotations

import asyncio
import copy
import json
import threading
from types import SimpleNamespace

import pytest
import pytest_asyncio
from aiohttp import web

from skport.assets import AssetManager, EnkaSource, enka_image, enka_item_image
from skport.assets.manifest import STORE_TABLES, git_blob_sha, parse_json
from skport.config import ClientConfig
from skport.errors import AssetError
from skport.transport import RetryPolicy, Transport

REV_A = "a" * 40
REV_B = "b" * 40


def tables(version: int = 1) -> dict:
    """Create small original-schema tables with a visible revision discriminator."""
    data = {name: {"1": {"version": version}} for name in STORE_TABLES}
    data["equips"] = {"Items": {"1": {"version": version}}, "Suits": {"1": {}}}
    data["gems"] = {"TermNums": {"1": {}}, "TemplateItems": {"1": {}}}
    data["weapon_meta"] = {
        "LevelCurves": {"1": [version]},
        "BreakSkillLevelBounds": {"1": {}},
        "TalentSkillLevelBounds": {"1": {}},
    }
    data["locs"] = {"en": {"1": f"Name {version}"}}
    return data


def encode(data: dict) -> dict[str, bytes]:
    return {name: json.dumps(value, separators=(",", ":")).encode() for name, value in data.items()}


@pytest_asyncio.fixture
async def source_server(http_server, tmp_path):
    resources = []

    async def start():
        state = SimpleNamespace(
            revision=REV_A,
            versions={REV_A: encode(tables()), REV_B: encode(tables(2))},
            calls=[],
            fail=None,
            mismatch=None,
            pause=None,
            pause_started=asyncio.Event(),
            release=asyncio.Event(),
        )

        async def handler(request):
            state.calls.append(request.path)
            assert not any(key in request.headers for key in ("cred", "salt", "sign", "sk-game-role"))
            if state.pause is not None and state.pause in request.path:
                state.pause = None
                state.pause_started.set()
                await state.release.wait()
            if request.path.startswith("/api/commits/"):
                if state.fail == "commit":
                    return web.Response(status=503)
                return web.json_response({"sha": state.revision})
            if request.path.startswith("/api/git/trees/"):
                revision = request.path.rsplit("/", 1)[-1]
                return web.json_response(
                    {
                        "tree": [
                            {
                                "type": "blob",
                                "path": f"store/ef/{name}.json",
                                "sha": "0" * 40 if state.mismatch == name else git_blob_sha(payload),
                                "size": len(payload),
                            }
                            for name, payload in state.versions[revision].items()
                        ],
                        "truncated": False,
                    }
                )
            if request.path.startswith("/raw/"):
                _, _, revision, _, _, filename = request.path.split("/")
                name = filename.removesuffix(".json")
                if state.fail == name:
                    return web.Response(status=503)
                return web.Response(body=state.versions[revision][name], content_type="application/json")
            return web.Response(status=404)

        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", handler)
        url = await http_server(app)
        config = ClientConfig(max_attempts=1, retry_backoff=0)
        transport = Transport(config)
        source = EnkaSource(
            transport,
            raw_base=url + "/raw",
            api_base=url + "/api",
            retry=RetryPolicy(attempts=1, backoff=0, jitter=0),
        )
        manager = AssetManager(config, transport, tmp_path / f"cache-{len(resources)}", source=source)
        resources.append((manager, transport))
        return manager, state

    yield start
    for manager, transport in resources:
        await manager.close()
        await transport.close()


async def test_commit_pinned_snapshot_and_exact_bytes(source_server):
    manager, state = await source_server()
    assert manager.current is None
    assert not manager.path.exists()
    snapshot = await manager.ensure()
    assert snapshot.revision == REV_A
    assert snapshot.tables["avatars"]["1"]["version"] == 1
    raw_requests = [path for path in state.calls if path.startswith("/raw/")]
    assert len(raw_requests) == 10
    assert all(f"/{REV_A}/store/ef/" in path for path in raw_requests)
    pointer = json.loads((manager.path / "current.json").read_text())
    folder = manager.path / "snapshots" / pointer["directory"]
    assert (folder / "avatars.json").read_bytes() == state.versions[REV_A]["avatars"]
    assert snapshot["locs"]["en"]["1"] == "Name 1"


async def test_same_revision_update_does_not_redownload_tables(source_server):
    manager, state = await source_server()
    original = await manager.ensure()
    state.calls.clear()
    result = await manager.update()
    assert result.snapshot is original
    assert result.changed is False
    assert state.calls == ["/api/commits/master"]


async def test_new_revision_reuses_unchanged_source_blobs(source_server):
    manager, state = await source_server()
    await manager.ensure()
    state.versions[REV_B] = copy.deepcopy(state.versions[REV_A])
    state.versions[REV_B]["avatars"] = encode(tables(2))["avatars"]
    state.revision = REV_B
    state.calls.clear()
    result = await manager.update()
    assert result.changed is True and result.previous_revision == REV_A
    assert result.revision == REV_B
    assert [path for path in state.calls if path.startswith("/raw/")] == [
        f"/raw/{REV_B}/store/ef/avatars.json"
    ]


@pytest.mark.parametrize("failure", ["avatars", "commit"])
async def test_failed_update_retains_current_snapshot_and_pointer(source_server, failure):
    manager, state = await source_server()
    original = await manager.ensure()
    old_pointer = (manager.path / "current.json").read_bytes()
    state.revision, state.fail = REV_B, failure
    with pytest.raises(AssetError):
        await manager.update()
    assert manager.current is original
    assert (manager.path / "current.json").read_bytes() == old_pointer
    assert await manager.ensure() is original


async def test_invalid_new_json_is_not_installed(source_server):
    manager, state = await source_server()
    original = await manager.ensure()
    old_pointer = (manager.path / "current.json").read_bytes()
    state.revision = REV_B
    state.versions[REV_B]["avatars"] = b'{"x":1,"x":2}'
    with pytest.raises(AssetError, match="duplicate"):
        await manager.update()
    assert manager.current is original
    assert (manager.path / "current.json").read_bytes() == old_pointer


async def test_source_blob_mismatch_rejected_before_disk_install(source_server):
    manager, state = await source_server()
    state.mismatch = "avatars"
    with pytest.raises(AssetError, match="integrity"):
        await manager.ensure()
    assert manager.current is None
    assert not (manager.path / "current.json").exists()


async def test_atomic_pointer_failure_keeps_previous_revision(source_server, monkeypatch):
    manager, state = await source_server()
    original = await manager.ensure()
    old_pointer = (manager.path / "current.json").read_bytes()
    state.revision = REV_B

    def fail_replace(source, destination):
        raise OSError("simulated pointer installation failure")

    monkeypatch.setattr("skport.assets.store.os.replace", fail_replace)
    with pytest.raises(AssetError, match="installed"):
        await manager.update()
    assert manager.current is original
    assert (manager.path / "current.json").read_bytes() == old_pointer


async def test_offline_reload_checks_hashes_and_never_requests_network(source_server):
    manager, state = await source_server()
    await manager.ensure()
    config = ClientConfig()
    config.assets_offline = True
    reopened = AssetManager(config, manager.transport, manager.path, source=manager.source)
    state.calls.clear()
    assert (await reopened.ensure()).revision == REV_A
    assert not state.calls
    pointer = json.loads((manager.path / "current.json").read_text())
    (manager.path / "snapshots" / pointer["directory"] / "avatars.json").write_text("{}")
    corrupted = AssetManager(config, manager.transport, manager.path, source=manager.source)
    with pytest.raises(AssetError, match="offline"):
        await corrupted.ensure()
    assert not state.calls
    await reopened.close()
    await corrupted.close()


async def test_cancelled_waiter_does_not_cancel_shared_ensure(source_server):
    manager, state = await source_server()
    state.pause = "commits"
    first = asyncio.create_task(manager.ensure())
    await state.pause_started.wait()
    second = asyncio.create_task(manager.ensure())
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    state.release.set()
    assert (await second).revision == REV_A
    assert len([path for path in state.calls if path.startswith("/api/commits")]) == 1


async def test_cached_ensure_survives_official_source_outage(source_server):
    manager, state = await source_server()
    await manager.ensure()
    reopened = AssetManager(manager.config, manager.transport, manager.path, source=manager.source)
    state.fail = "commit"
    assert (await reopened.ensure()).revision == REV_A
    await reopened.close()


async def test_concurrent_updates_share_one_refresh(source_server):
    manager, state = await source_server()
    await manager.ensure()
    state.revision, state.pause = REV_B, "commits"
    state.calls.clear()
    first = asyncio.create_task(manager.update())
    await state.pause_started.wait()
    second = asyncio.create_task(manager.update())
    await asyncio.sleep(0)
    state.release.set()
    a, b = await asyncio.gather(first, second)
    assert a is b
    assert len([path for path in state.calls if path.startswith("/api/commits")]) == 1


async def test_shutdown_finishes_atomic_install_before_return(source_server, monkeypatch):
    manager, state = await source_server()
    await manager.ensure()
    state.revision = REV_B
    entered = threading.Event()
    release = threading.Event()
    install = manager._install

    def slow_install(acquired):
        entered.set()
        assert release.wait(2)
        install(acquired)

    monkeypatch.setattr(manager, "_install", slow_install)
    update = asyncio.create_task(manager.update())
    assert await asyncio.to_thread(entered.wait, 2)
    closing = asyncio.create_task(manager.close())
    try:
        await asyncio.sleep(0)
        assert not closing.done()
    finally:
        release.set()
    await closing
    with pytest.raises(asyncio.CancelledError):
        await update
    pointer = json.loads((manager.path / "current.json").read_text())
    assert pointer["directory"].startswith(REV_B)


@pytest.mark.parametrize("payload", ['{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', '{"x":1,"x":2}', "[]"])
def test_asset_json_rejects_invalid_semantics(payload):
    with pytest.raises(AssetError):
        parse_json(payload, "fixture")


@pytest.mark.parametrize(
    "path,expected",
    [
        ("icon/avatar", "https://enka.network/ui/ef/icon/avatar.png"),
        ("/ui/ef/icon/avatar.png", "https://enka.network/ui/ef/icon/avatar.png"),
        ("https://enka.network/ui/ef/icon/avatar.png", "https://enka.network/ui/ef/icon/avatar.png"),
        (None, None),
    ],
)
def test_canonical_image_links(path, expected):
    assert enka_image(path) == expected


def test_canonical_image_rejects_parent_paths_and_other_hosts():
    for path in ("../token", "https://elsewhere.invalid/image.png", "icon?token=x"):
        with pytest.raises(AssetError):
            enka_image(path)


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/ui/ef/wpn_pistol_0010.png", "https://enka.network/ui/ef/itemicon/wpn_pistol_0010.png"),
        ("/ui/ef/item_gem_rarity_5.png", "https://enka.network/ui/ef/itemicon/item_gem_rarity_5.png"),
        ("/ui/ef/itemicon/item_equip.png", "https://enka.network/ui/ef/itemicon/item_equip.png"),
        (None, None),
    ],
)
def test_item_image_directory_normalizes_original_store_paths(path, expected):
    assert enka_item_image(path) == expected


@pytest.mark.parametrize(
    "table,entry",
    [
        ("weapons", {"LevelTemplateId": "missing"}),
        ("weapons", {"SkillList": ["missing"]}),
        ("equips", {"Items": {"1": {"SuitId": "missing"}}, "Suits": {"1": {}}}),
        ("equips", {"Items": {"1": {}}, "Suits": {"1": {"SkillId": "missing"}}}),
    ],
)
async def test_missing_calculation_cross_reference_is_not_installed(source_server, table, entry):
    manager, state = await source_server()
    original = await manager.ensure()
    state.revision = REV_B
    data = tables(2)
    data[table] = entry if table == "equips" else {"1": entry}
    state.versions[REV_B] = encode(data)
    with pytest.raises(AssetError, match="missing"):
        await manager.update()
    assert manager.current is original
