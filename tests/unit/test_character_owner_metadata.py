"""Every normalized character lookup includes its fetched player identity."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from skport import ClientConfig, Role, Target
from skport.games.endfield.client import EndfieldClient
from skport.games.endfield.models import CharacterBuild, CharacterIdentity, PlayerIdentity


@pytest.fixture
def character_client() -> EndfieldClient:
    record = {"id": "opaque-character", "charData": {"name": "Operator"}}
    public_target = Target("public-social", "public-role", "3")
    raw = SimpleNamespace(
        role_for=AsyncMock(return_value=Role("owner-role", "2")),
        detail=AsyncMock(return_value={"detail": {"base": {"name": "Public player"}, "chars": [record]}}),
        owned_card=AsyncMock(return_value={"detail": {"base": {"name": "Owner player"}, "chars": [record]}}),
        character=AsyncMock(return_value={"detail": record}),
        owned_character=AsyncMock(return_value={"detail": record}),
    )
    api = SimpleNamespace(
        config=ClientConfig(),
        endfield=raw,
        resolve_target=AsyncMock(return_value=public_target),
        pool=SimpleNamespace(credential_for=AsyncMock(return_value=SimpleNamespace(user_id="owner-social"))),
    )

    def builds(records: list[dict], player: PlayerIdentity, locale: str) -> list[CharacterBuild]:
        return [
            CharacterBuild(identity=CharacterIdentity(skport_id=item["id"]), owner=player, locale=locale)
            for item in records
        ]

    client = EndfieldClient(api)
    client._build_service = SimpleNamespace(characters=AsyncMock(side_effect=builds))
    return client


@pytest.mark.parametrize("scope", ["public", "owner"])
@pytest.mark.parametrize("selector", [{"char_id": "opaque-character"}, {"name": "Operator"}, {"index": 0}])
@pytest.mark.parametrize("full", [True, False])
async def test_normalized_lookup_has_named_owner_without_duplicate_snapshot_fetch(
    character_client: EndfieldClient, scope: str, selector: dict[str, object], full: bool
) -> None:
    if scope == "public":
        build = await character_client.character(skport_id="public-social", lang="ko", full=full, **selector)
        snapshot, detail = character_client.raw.detail, character_client.raw.character
        assert (build.owner.skport_id, build.owner.game_uid, build.owner.server_id, build.owner.name) == (
            "public-social", "public-role", "3", "Public player"
        )
        snapshot.assert_awaited_once_with(Target("public-social", "public-role", "3"), lang="ko")
        character_client.raw.owned_card.assert_not_awaited()
        character_client.raw.owned_character.assert_not_awaited()
    else:
        build = await character_client.owned_character(token="owner-token", lang="ko", full=full, **selector)
        snapshot, detail = character_client.raw.owned_card, character_client.raw.owned_character
        assert (build.owner.skport_id, build.owner.game_uid, build.owner.server_id, build.owner.name) == (
            "owner-social", "owner-role", "2", "Owner player"
        )
        snapshot.assert_awaited_once_with(token="owner-token", role=Role("owner-role", "2"), lang="ko")
        character_client.api.pool.credential_for.assert_awaited_once_with("owner-token")
        character_client.api.resolve_target.assert_not_awaited()
        character_client.raw.detail.assert_not_awaited()
        character_client.raw.character.assert_not_awaited()
    assert isinstance(build, CharacterBuild)
    assert build.identity.skport_id == "opaque-character" and build.locale == "ko"
    assert detail.await_count == int(full)
    character_client.builds.characters.assert_awaited_once()


@pytest.mark.parametrize("scope", ["public", "owner"])
async def test_raw_direct_id_lookup_retains_single_character_fetch(
    character_client: EndfieldClient, scope: str
) -> None:
    if scope == "public":
        record = await character_client.character(skport_id="public-social", char_id="opaque-character", raw=True)
        character_client.raw.character.assert_awaited_once()
    else:
        record = await character_client.owned_character(token="owner-token", char_id="opaque-character", raw=True)
        character_client.raw.owned_character.assert_awaited_once()
    assert record["id"] == "opaque-character"
    character_client.raw.detail.assert_not_awaited()
    character_client.raw.owned_card.assert_not_awaited()
    character_client.api.pool.credential_for.assert_not_awaited()
    character_client.builds.characters.assert_not_awaited()
