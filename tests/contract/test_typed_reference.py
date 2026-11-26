"""Exercise typed owner and reference helpers using SKPORT response captures."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from skport import AlreadyCheckedIn, AuthError, SkportClient
from skport.errors import APIError, DecodeError, check_envelope
from skport.games.endfield.endpoints import ATTENDANCE
from skport.games.endfield.models import AttendanceStatus, CheckInResult, EnumCatalog, Inventory, Notice

FIXTURES = Path(__file__).parents[1] / "fixtures" / "skport"
TOKEN = "test-owner-token"


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_attendance_preserves_raw_default_and_normalizes_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    response = fixture("attendance")
    async with SkportClient(tokens=[TOKEN]) as client:
        raw = AsyncMock(return_value=response)
        monkeypatch.setattr(client.endfield.raw, "attendance", raw)

        assert await client.endfield.attendance(token=TOKEN) == response
        status = await client.endfield.attendance(token=TOKEN, raw=False)

    assert isinstance(status, AttendanceStatus)
    assert len(status.calendar) == len(response["calendar"])
    assert len(status.first) == len(response["first"])
    assert status.has_today == response["hasToday"]
    assert status.current_at == datetime.fromtimestamp(int(response["currentTs"]), UTC)
    assert [day.award_id for day in status.available_days] == [
        day["awardId"] for day in response["calendar"] + response["first"] if day["available"] and not day["done"]
    ]
    assert all(reward.id and reward.count > 0 for reward in status.rewards_by_id.values())


@pytest.mark.asyncio
async def test_check_in_preserves_award_order_and_missing_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = fixture("attendance")["resourceInfoMap"]
    award_id, reward = next(iter(captured.items()))
    response = {
        "ts": "0",
        "awardIds": [{"id": "unlisted-reward", "type": 97}, {"id": award_id, "type": 1}],
        "tomorrowAwardIds": [{"id": award_id, "type": 1}],
        "resourceInfoMap": {award_id: reward},
    }
    async with SkportClient(tokens=[TOKEN]) as client:
        request = AsyncMock(return_value=response)
        monkeypatch.setattr(client.endfield.raw, "check_in", request)

        result = await client.endfield.check_in(token=TOKEN, raw=False)
        request.assert_awaited_once_with(token=TOKEN, role=None, lang=None)

        assert isinstance(result, CheckInResult)
        assert result.claimed_at is None
        assert result.awards[0].type == 97
        assert result.rewards == [None, result.rewards_by_id[award_id]]
        assert result.tomorrow_rewards == [result.rewards_by_id[award_id]]
        assert await client.endfield.check_in(token=TOKEN) == response


@pytest.mark.parametrize(
    "status,path,method,message,exception",
    [
        (200, ATTENDANCE, "POST", "Please do not sign in again!", AlreadyCheckedIn),
        (200, ATTENDANCE, "GET", "Please do not sign in again!", APIError),
        (200, "/different-endpoint", "POST", "Please do not sign in again!", APIError),
        (200, ATTENDANCE, "POST", "Session expired", AuthError),
        (401, ATTENDANCE, "POST", "Please do not sign in again!", AuthError),
        (200, ATTENDANCE, "POST", "Game role not eligible", APIError),
    ],
)
def test_check_in_error_is_scoped_to_daily_claim(status, path, method, message, exception) -> None:
    with pytest.raises(exception) as caught:
        check_envelope({"code": 10001, "message": message}, status=status, path=path, method=method)
    assert type(caught.value) is exception


@pytest.mark.asyncio
async def test_inventory_retains_ownership_and_unknown_quantity(monkeypatch: pytest.MonkeyPatch) -> None:
    response = fixture("inventory")
    wire = response["userGameData"]
    wire["userEquips"]["fixture-zero"] = {"equipId": "fixture-zero", "ownedCount": 0}
    async with SkportClient(tokens=[TOKEN]) as client:
        monkeypatch.setattr(client.endfield.raw, "inventory", AsyncMock(return_value=response))

        assert await client.endfield.inventory(token=TOKEN) == response
        inventory = await client.endfield.inventory(token=TOKEN, raw=False)

    assert isinstance(inventory, Inventory)
    assert inventory.game_uid == wire["roleId"]
    for operator in inventory.operators.values():
        source = wire["userChars"][operator.id]
        assert operator.owned == source["owned"]
        assert operator.count is None
        assert operator.level == (int(source["level"]) if source.get("level") is not None else None)
        assert {key: skill.level for key, skill in operator.skills.items()} == {
            key: int(skill["level"]) for key, skill in source.get("userSkills", {}).items()
        }
    assert all(weapon.count is None for weapon in inventory.weapons.values())
    assert not inventory.equipment["fixture-zero"].owned
    assert inventory.equipment["fixture-zero"].count == 0


@pytest.mark.asyncio
async def test_reference_reads_normalize_language_and_notice_text(monkeypatch: pytest.MonkeyPatch) -> None:
    enum_data = fixture("enums")
    news_data = fixture("news")
    async with SkportClient(tokens=[TOKEN]) as client:
        enum_read, news_read = AsyncMock(return_value=enum_data), AsyncMock(return_value=news_data)
        monkeypatch.setattr(client.endfield.raw, "enums", enum_read)
        monkeypatch.setattr(client.endfield.raw, "news", news_read)

        catalog = await client.endfield.enums(lang="en-US")
        notices = await client.endfield.news(lang="en-US")

    enum_read.assert_awaited_once_with(lang="en")
    news_read.assert_awaited_once_with(lang="en")
    assert isinstance(catalog, EnumCatalog)
    first_enum = enum_data["professions"][0]
    assert catalog.label("professions", first_enum["key"]).name == first_enum["value"]
    assert catalog.label("missing", "key") is None
    assert all(isinstance(notice, Notice) and notice.locale == "en" for notice in notices)
    assert [notice.title for notice in notices] == [row["title"] for row in news_data["list"]]
    assert any(notice.text for notice in notices)
    assert all("<div" not in notice.text and "<style" not in notice.text for notice in notices)


@pytest.mark.asyncio
async def test_typed_attendance_rejects_invalid_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    async with SkportClient(tokens=[TOKEN]) as client:
        monkeypatch.setattr(
            client.endfield.raw, "attendance", AsyncMock(return_value={"calendar": {"not": "a list"}})
        )
        with pytest.raises(DecodeError, match="calendar"):
            await client.endfield.attendance(token=TOKEN, raw=False)
