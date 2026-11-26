"""Owner roster selection stays attached to the explicit account token."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from skport import ClientConfig, ConfigError, Role, TargetNotFound
from skport.games.endfield.client import EndfieldClient


@pytest.fixture
def owner_client() -> EndfieldClient:
    records = [
        {"id": "owner-first", "charData": {"name": "First"}, "level": 80},
        {"id": "owner-second", "charData": {"name": "Second"}, "level": 70},
    ]
    selected = Role("owner-role", "2")
    raw = SimpleNamespace(
        role_for=AsyncMock(return_value=selected),
        owned_card=AsyncMock(
            return_value={
                "detail": {
                    "base": {"name": "Owner"},
                    "chars": records,
                    "config": {"charIds": ["owner-second"]},
                }
            }
        ),
        owned_character=AsyncMock(return_value={"detail": {**records[0], "detailed": True}}),
        detail=AsyncMock(side_effect=AssertionError("owner reads cannot use a public card")),
        character=AsyncMock(side_effect=AssertionError("owner reads cannot use public character auth")),
    )
    api = SimpleNamespace(
        config=ClientConfig(),
        endfield=raw,
        pool=SimpleNamespace(credential_for=AsyncMock(return_value=SimpleNamespace(user_id="owner-social"))),
        resolve_target=AsyncMock(side_effect=AssertionError("owner reads cannot resolve a public target")),
    )
    client = EndfieldClient(api)
    client._build_service = SimpleNamespace(characters=AsyncMock(return_value=["normalized-owner-build"]))
    return client


async def test_owner_roster_includes_characters_outside_showcase(owner_client: EndfieldClient) -> None:
    records = await owner_client.owned_characters(token="owner-token", raw=True)
    assert [item["id"] for item in records] == ["owner-first", "owner-second"]
    owner_client.raw.owned_card.assert_awaited_once_with(
        token="owner-token", role=Role("owner-role", "2"), lang=None
    )
    owner_client.raw.owned_character.assert_not_awaited()


async def test_owner_direct_id_preserves_operator_and_skips_roster(owner_client: EndfieldClient) -> None:
    record = await owner_client.owned_character(
        token="owner-token", char_id="owner-first", operator_id="operator-first", lang="ja", raw=True
    )
    assert record["detailed"] is True
    owner_client.raw.owned_card.assert_not_awaited()
    owner_client.raw.owned_character.assert_awaited_once_with(
        token="owner-token",
        char_id="owner-first",
        operator_id="operator-first",
        role=Role("owner-role", "2"),
        lang="ja",
    )


@pytest.mark.parametrize("selector", [{"name": " ＦＩＲＳＴ "}, {"index": 0}])
async def test_owner_selectors_use_full_roster_and_owner_auth(
    owner_client: EndfieldClient, selector: dict[str, object]
) -> None:
    record = await owner_client.owned_character(token="owner-token", raw=True, **selector)
    assert record["id"] == "owner-first" and record["detailed"] is True
    owner_client.raw.owned_character.assert_awaited_once_with(
        token="owner-token",
        char_id="owner-first",
        operator_id=None,
        role=Role("owner-role", "2"),
        lang=None,
    )


async def test_owner_summary_keeps_owner_player_metadata(owner_client: EndfieldClient) -> None:
    build = await owner_client.owned_character(token="owner-token", index=1, full=False, lang="ko")
    assert build == "normalized-owner-build"
    owner_client.raw.owned_character.assert_not_awaited()
    owner_client.api.pool.credential_for.assert_awaited_once_with("owner-token")
    records, player, language = owner_client.builds.characters.await_args.args
    assert records[0]["id"] == "owner-second"
    assert (player.skport_id, player.game_uid, player.name, language) == (
        "owner-social", "owner-role", "Owner", "ko"
    )


@pytest.mark.parametrize(
    "selector",
    [{}, {"char_id": "owner-first", "index": 0}, {"char_id": ""}, {"char_id": "owner-first", "operator_id": ""}],
)
async def test_owner_selector_errors_precede_auth(owner_client: EndfieldClient, selector: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        await owner_client.owned_character(token="owner-token", raw=True, **selector)
    owner_client.raw.role_for.assert_not_awaited()


async def test_owner_missing_name_never_fetches_a_different_character(owner_client: EndfieldClient) -> None:
    with pytest.raises(TargetNotFound):
        await owner_client.owned_character(token="owner-token", name="Public character", raw=True)
    owner_client.raw.owned_character.assert_not_awaited()


async def test_owner_single_character_requires_explicit_token(owner_client: EndfieldClient) -> None:
    with pytest.raises(TypeError):
        await owner_client.owned_character(char_id="owner-first")
    owner_client.raw.role_for.assert_not_awaited()
