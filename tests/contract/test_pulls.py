"""Offline coverage for owner-scoped pull sync and persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from skport import SkportClient
from skport.errors import ConfigError, DecodeError
from skport.games.endfield import endpoints as ep
from skport.games.endfield.identity import Role
from skport.games.endfield.models.identity import PlayerIdentity
from skport.games.endfield.models.pulls import PullHistory

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "skport"
_SPECIAL = "E_CharacterGachaPoolType_Special"
_RERUN = "E_CharacterGachaPoolType_Rerun"


def _capture(name: str) -> Any:
    return json.loads((_FIXTURES / (name + ".json")).read_text(encoding="utf-8"))


class _Records:
    def __init__(self) -> None:
        self.pools: list[dict[str, Any]] = []
        self.pages: dict[tuple[str, str], dict[str, Any]] = {}
        self.calls: list[tuple[str, str]] = []

    async def page(self, path: str, *, parameters: dict[str, str], **_: Any) -> Any:
        if path == ep.WEAPON_POOLS:
            return self.pools
        pool = parameters["pool_type"] if path == ep.CHAR_PULLS else parameters["pool_id"]
        query = (pool, parameters.get("seq_id", ""))
        self.calls.append(query)
        return self.pages.get(query, {"list": [], "hasMore": False})


@pytest.fixture
async def owner_client(monkeypatch: pytest.MonkeyPatch) -> Any:
    records = _Records()

    async def role_for(*_: Any, **__: Any) -> Role:
        return Role("game-owner", "3", nickname="Example Player")

    async def credential_for(_: str) -> SimpleNamespace:
        return SimpleNamespace(user_id="social-owner")

    async with SkportClient(tokens=["fixture-token"]) as client:
        monkeypatch.setattr(client.api.pool, "credential_for", credential_for)
        monkeypatch.setattr(client.endfield.raw, "role_for", role_for)
        monkeypatch.setattr(client.endfield.raw.pulls, "_owned_page", records.page)
        yield client, records


def _row(sequence: int, rarity: int = 4, *, free: bool = False, pool: str = "banner-a") -> dict[str, Any]:
    return {
        "kind": "draw",
        "poolId": pool,
        "poolName": "Example Banner",
        "seqId": str(sequence),
        "gachaTs": str(1_790_000_000_000 + sequence),
        "charId": "operator-example",
        "charName": "Example Operator",
        "rarity": rarity,
        "isFree": free,
        "isNew": False,
    }


async def test_captured_pull_pages_and_incremental_overlap(owner_client: Any) -> None:
    client, records = owner_client
    first = _capture("pull_character_special")
    last = _capture("pull_character_next")
    records.pools = _capture("pull_weapon_pools")
    empty_weapon = _capture("pull_weapon_empty")
    for pool in records.pools:
        records.pages[pool["poolId"], ""] = empty_weapon
    cursor = str(first["list"][-1]["seqId"])
    records.pages[_SPECIAL, ""] = first
    records.pages[_SPECIAL, cursor] = last

    history = await client.endfield.pulls(token="fixture-token")
    assert history.player.game_uid == "game-owner"
    assert history.totals.character_draws == len(first["list"]) + len(last["list"])
    assert len(history.pools) == len(records.pools)
    assert history.records[0].item.name == first["list"][0]["charName"]
    assert history.records[0].pulled_at == datetime.fromtimestamp(int(first["list"][0]["gachaTs"]) / 1000, UTC)
    assert (_SPECIAL, cursor) in records.calls
    assert not history.complete_history

    records.calls.clear()
    synced = await client.endfield.pulls(token="fixture-token", since=history)
    assert synced == history
    assert (_SPECIAL, cursor) not in records.calls
    assert synced.records is not history.records


async def test_captured_rerun_retains_pool_version(owner_client: Any) -> None:
    client, records = owner_client
    page = _capture("pull_character_rerun")
    records.pages[_RERUN, ""] = page
    history = await client.endfield.pulls(token="fixture-token")
    assert history.records
    assert [row.pool_version for row in history.records] == [row["poolVersion"] for row in page["list"]]


async def test_pity_counts_paid_draws_across_limited_streams_and_weapon_separately(owner_client: Any) -> None:
    client, records = owner_client
    recent_gift = _row(19)
    del recent_gift["charId"], recent_gift["rarity"]
    recent_gift.update(kind="gift", nameText="Example Gift")
    records.pages[_SPECIAL, ""] = {"list": [recent_gift, _row(18, 6, free=True), _row(17)], "hasMore": False}
    records.pages[_RERUN, ""] = {"list": [_row(15, 6, pool="banner-b")], "hasMore": False}
    records.pools = [{"poolId": "weapon-pool", "poolName": "Example Weapons", "online": True}]
    weapon_row = _row(16, pool="weapon-pool")
    del weapon_row["isFree"]
    weapon_row.update(weaponId="weapon-example", weaponName="Example Weapon")
    records.pages["weapon-pool", ""] = {"list": [weapon_row], "hasMore": False}

    history = await client.endfield.pulls(token="fixture-token")
    pity = {counter.banner_id: counter for counter in history.pity}
    assert history.totals.model_dump() == {
        "character_draws": 3, "weapon_draws": 1, "free_draws": 1, "six_star_draws": 2, "gifts": 1,
    }
    assert history.records[0].is_draw is False and not history.records[0].item.id
    assert pity["banner-a"].current == pity["banner-b"].current == 1
    assert pity["banner-a"].hard_limit == 80 and pity["banner-a"].featured_guarantee == 120
    assert pity["banner-a"].featured_received is None
    assert pity["weapon-pool"].current is None and pity["weapon-pool"].hard_limit == 40
    assert pity["weapon-pool"].observed_since_six_star == 1
    assert next(cp for cp in history.checkpoints if cp.stream.pool_id == _SPECIAL).sequence_id == "19"


async def test_missing_previous_sequence_keeps_records_and_marks_a_gap(owner_client: Any) -> None:
    client, records = owner_client
    records.pages[_SPECIAL, ""] = {"list": [_row(2, 6)], "hasMore": False}
    history = await client.endfield.pulls(token="fixture-token")
    assert history.pity[0].current == 0
    records.pages[_SPECIAL, ""] = {"list": [_row(3)], "hasMore": False}
    synced = await client.endfield.pulls(token="fixture-token", since=history)
    assert [row.sequence_id for row in synced.records] == ["3", "2"]
    assert synced.pity[0].current is None and synced.pity[0].observed_since_six_star == 1
    assert any(issue.code == "pull_history_gap" for issue in synced.issues)
    assert (await client.endfield.pulls(token="fixture-token", since=synced)).issues == synced.issues


async def test_gap_in_another_limited_stream_makes_shared_pity_unknown(owner_client: Any) -> None:
    client, records = owner_client
    records.pages[_SPECIAL, ""] = {"list": [_row(5, 6)], "hasMore": False}
    records.pages[_RERUN, ""] = {"list": [_row(3, pool="banner-b")], "hasMore": False}
    history = await client.endfield.pulls(token="fixture-token")
    assert all(counter.current == 0 for counter in history.pity)

    records.pages[_RERUN, ""] = {"list": [_row(8, pool="banner-b")], "hasMore": False}
    history = await client.endfield.pulls(token="fixture-token", since=history)
    assert all(counter.current is None and counter.observed_since_six_star == 1 for counter in history.pity)


async def test_featured_evidence_requires_known_id_paid_six_star_and_exact_banner(owner_client: Any) -> None:
    client, records = owner_client
    rerun = {**_row(15, 6, pool="banner-b"), "poolVersion": 2}
    records.pages[_SPECIAL, ""] = {"list": [_row(18, 6, free=True), _row(17, 5)], "hasMore": False}
    records.pages[_RERUN, ""] = {"list": [rerun], "hasMore": False}
    featured = {
        ("character:" + _SPECIAL, "banner-a", None): {"operator-example"},
        ("character:" + _RERUN, "banner-b", 2): {"operator-example"},
    }

    history = await client.endfield.pulls(token="fixture-token", featured_items=featured)
    assert [counter.featured_received for counter in history.pity] == [None, True]
    synced = await client.endfield.pulls(token="fixture-token", since=history)
    assert synced.pity == history.pity
    swapped = await client.endfield.pulls(
        token="fixture-token",
        since=synced,
        featured_items={("character:" + _RERUN, "banner-b", 2): {"other-operator"}},
    )
    assert [counter.featured_received for counter in swapped.pity] == [None, None]


async def test_after_is_exclusive_and_requires_timezone(owner_client: Any) -> None:
    client, records = owner_client
    records.pages[_SPECIAL, ""] = {"list": [_row(3), _row(2)], "hasMore": True}
    boundary = datetime.fromtimestamp(int(_row(2)["gachaTs"]) / 1000, UTC)

    with pytest.raises(ConfigError, match="timezone-aware"):
        await client.endfield.pulls(token="fixture-token", after=boundary.replace(tzinfo=None))
    history = await client.endfield.pulls(token="fixture-token", after=boundary)
    assert [row.sequence_id for row in history.records] == ["3"]
    assert (_SPECIAL, "2") not in records.calls
    assert not next(cp for cp in history.checkpoints if cp.stream.pool_id == _SPECIAL).reached_end


async def test_saved_owner_is_checked_before_any_record_request(owner_client: Any) -> None:
    client, records = owner_client
    history = PullHistory(player=PlayerIdentity(skport_id="social-owner", game_uid="other-game-owner", server_id="3"))
    with pytest.raises(ConfigError, match="different SKPORT account or Endfield role"):
        await client.endfield.pulls(token="fixture-token", since=history)
    assert not records.calls


@pytest.mark.parametrize("page", [{"list": [], "hasMore": True}, {"list": [_row(2)], "hasMore": True}])
async def test_typed_continuation_rejects_missing_or_looping_cursor(owner_client: Any, page: Any) -> None:
    client, records = owner_client
    records.pages[_SPECIAL, ""] = records.pages[_SPECIAL, "2"] = page
    with pytest.raises(DecodeError, match="continuation cursor"):
        await client.endfield.pulls(token="fixture-token")


async def test_pull_history_json_and_csv_round_trip(owner_client: Any, tmp_path: Path) -> None:
    client, records = owner_client
    records.pages[_SPECIAL, ""] = {"list": [_row(12), _row(11, 6)], "hasMore": False}
    history = await client.endfield.pulls(token="fixture-token")
    json_path, csv_path = tmp_path / "pulls.json", tmp_path / "pulls.csv"

    history.save(json_path)
    assert PullHistory.load(json_path) == history
    assert "fixture-token" not in json_path.read_text(encoding="utf-8")
    history.to_csv(csv_path)
    imported = PullHistory.from_csv(csv_path, player=history.player)
    assert imported.records == history.records
    assert imported.totals == history.totals
    assert not imported.checkpoints and not imported.complete_history

    PullHistory(player=history.player).to_csv(csv_path)
    assert PullHistory.from_csv(csv_path, player=history.player) == PullHistory(player=history.player)
