"""Check normalized models against de-identified SKPORT responses."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from skport import ClientConfig, ImageSource
from skport.assets import AssetSnapshot
from skport.games.endfield.clean.character import build_character
from skport.games.endfield.clean.endgame import build_contract_report, build_monument_report
from skport.games.endfield.clean.profile import build_player_card
from skport.games.endfield.clean.progress import build_live_status
from skport.games.endfield.clean.world import build_factory_state
from skport.games.endfield.identity import Target, parse_roles, select_role
from skport.games.endfield.models import CalculationState, EquipmentSlot, PlayerIdentity

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def read_snapshot(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / "skport" / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def player() -> PlayerIdentity:
    role = select_role(parse_roles(read_snapshot("owner_binding")))
    return PlayerIdentity(skport_id="fixture-user", game_uid=role.role_id, server_id=role.server_id)


def test_default_role_matches_captured_binding() -> None:
    data = read_snapshot("owner_binding")
    app = data["list"][0]
    binding = app["bindingList"][0]
    role = select_role(parse_roles(data))

    assert role.role_id == str(binding["defaultRole"]["roleId"])
    assert role.server_id == str(binding["defaultRole"]["serverId"])
    assert role.account_uid == app["defaultUid"]
    assert role.is_default is True
    assert role.is_default_binding is True


def test_profile_retains_ownership_showcase_and_snapshot_clock(player: PlayerIdentity) -> None:
    data = read_snapshot("profile_snapshot")
    detail = data["detail"]
    target = Target(player.skport_id, player.game_uid, player.server_id)
    config = ClientConfig(calculate_stats=False)
    roster = [build_character(row, None, config, owner=player) for row in detail["chars"]]

    card = build_player_card(data, roster, target, "en", ImageSource.SKPORT)

    assert card.player.game_uid == detail["base"]["roleId"]
    assert card.counts.characters == detail["base"]["charNum"] > len(card.characters)
    assert card.roster_complete is False
    assert card.showcase_ids == detail["config"]["charIds"]
    assert [medal.id for medal in card.medals] == [
        detail["achieve"]["display"][str(medal.slot)] for medal in card.medals
    ]
    assert card.medals
    assert card.snapshot_at == datetime.fromtimestamp(int(detail["base"]["saveTime"]), UTC)
    assert card.server_time == datetime.fromtimestamp(int(detail["currentTs"]), UTC)


def test_profile_activity_and_factory_use_captured_sections(player: PlayerIdentity) -> None:
    data = read_snapshot("profile_snapshot")
    detail = data["detail"]
    live = build_live_status(data, player, ImageSource.SKPORT)
    factory = build_factory_state(data, player, ImageSource.SKPORT)

    assert live.sanity is not None
    assert live.sanity.current == int(detail["dungeon"]["curStamina"])
    assert live.credits is not None
    assert live.credits.refresh_at == datetime.fromtimestamp(int(detail["credit"]["nextRefreshTs"]), UTC)
    assert [cabin.id for cabin in factory.cabins] == [room["id"] for room in detail["spaceShip"]["rooms"]]
    assert any(cabin.crew for cabin in factory.cabins)
    assert len(factory.regions) == len(detail["domain"])


def test_character_keeps_weapon_essence_and_equipment_without_asset_tables(player: PlayerIdentity) -> None:
    data = read_snapshot("character_snapshot")["detail"]
    build = build_character(data, None, ClientConfig(calculate_stats=False), owner=player)

    assert build.identity.skport_id == data["id"]
    assert build.name == data["charData"]["name"]
    assert build.calculation_state is CalculationState.NOT_REQUESTED
    assert build.stats is None
    assert {piece.slot for piece in build.equipment} == set(EquipmentSlot)
    assert build.weapon is not None and build.weapon.gem is not None
    assert [term.points for term in build.weapon.gem.terms] == [
        term["cost"] for term in data["weapon"]["gem"]["terms"]
    ]
    assert build.tactical_item is not None


def test_captured_character_calculates_reference_stats(player: PlayerIdentity) -> None:
    raw = read_snapshot("character_snapshot")["detail"]
    tables_path = FIXTURES / "calculation" / "skport-sample-tables.json"
    sample = json.loads(tables_path.read_text(encoding="utf-8"))
    snapshot = AssetSnapshot(sample["revision"], sample["tables"], sample["fetched_at"])

    build = build_character(raw, snapshot, ClientConfig(missing_assets="raise"), owner=player)

    assert build.calculation_state is CalculationState.CALCULATED
    assert build.asset_revision == snapshot.revision
    assert build.stats is not None
    assert (build.stats.hp, build.stats.attack, build.stats.defense) == (6040, 3977, 140)
    assert (build.stats.strength, build.stats.agility, build.stats.intellect, build.stats.will) == (
        109,
        230,
        671,
        160,
    )
    assert build.stats.critical_rate == pytest.approx(0.491675, abs=1e-12)
    sources = {entry.source.split(":", 1)[0] for entry in build.stats.contributions}
    assert {"character", "weapon", "equipment", "suit", "talent", "derived"} <= sources


def test_monument_keeps_clear_flags_and_completed_runs(player: PlayerIdentity) -> None:
    data = read_snapshot("monument_snapshot")
    report = build_monument_report(data, player, ImageSource.SKPORT)

    assert [event.id for event in report.events] == [
        event["id"] for event in data["indieHard"]["indieHardGroups"]
    ]
    stages = [stage for event in report.events for stage in event.stages]
    assert any(
        stage.normal_cleared and stage.normal and stage.normal.completed and stage.normal.team
        for stage in stages
    )
    assert any(not stage.normal_cleared and stage.normal is None for stage in stages)
    assert all(not stage.hard_cleared and stage.hard is None for stage in stages)


def test_contract_keeps_indicator_order_and_empty_history(player: PlayerIdentity) -> None:
    data = read_snapshot("contract_snapshot")
    wire = data["crisisContract"]
    report = build_contract_report(data, player, ImageSource.SKPORT)

    assert report.current is not None
    assert report.current.runs == []
    assert report.current.stage_id == wire["dungeon"]["id"]
    assert report.current.stage_recommended_level == wire["dungeon"]["recommendLevel"]
    assert [item.id for item in report.current.modifiers] == [item["id"] for item in wire["indicators"]]
    assert [enemy.id for enemy in report.current.enemies] == [
        enemy["id"] for enemy in wire["dungeon"]["enemies"]
    ]
