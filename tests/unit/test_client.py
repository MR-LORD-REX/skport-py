"""Facade ownership, game extensibility, and raw character selection."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from skport import ClientConfig, ConfigError, Language, SkportClient, TargetNotFound
from skport.games.endfield import EndfieldClient, Target
from skport.games.registry import GameRegistry


@pytest.fixture
def api():
    records = [
        {"id": "first", "charData": {"name": "Example"}, "level": 20, "futureField": 7},
        {"id": "second", "charData": {"name": "另一个"}, "level": 30},
        {"id": "third", "charData": {"name": "Third"}, "level": 40},
    ]
    raw = SimpleNamespace(
        resolve_target=AsyncMock(return_value=Target("social", "role", "2")),
        detail=AsyncMock(
            return_value={"detail": {"chars": records, "config": {"charIds": ["third", "first"]}}}
        ),
        character=AsyncMock(return_value={"detail": {"id": "full", "extraField": True}}),
        attendance=AsyncMock(return_value={"calendar": []}),
        check_in=AsyncMock(return_value={"awards": []}),
        inventory=AsyncMock(return_value={"owned": {}}),
    )
    return SimpleNamespace(
        config=ClientConfig(),
        transport=SimpleNamespace(),
        endfield=raw,
        warm=AsyncMock(),
        close=AsyncMock(),
        user=AsyncMock(return_value={"user": {"nickname": "Public"}}),
        resolve_target=raw.resolve_target,
    )


@pytest.mark.asyncio
async def test_borrowed_api_survives_facade_and_game_close(api):
    async with SkportClient(api=api) as client:
        assert client.endfield is client.game(" ENDFIELD ")
        assert client.endfield.api is api
        await client.endfield.close()
    api.close.assert_not_awaited()
    with pytest.raises(ConfigError, match="closed"):
        client.game("endfield")


@pytest.mark.asyncio
async def test_owned_api_closes_once_and_config_override_does_not_mutate(monkeypatch, api):
    captured = {}

    def create_api(tokens, *, config):
        captured.update(tokens=tokens, config=config)
        return api

    monkeypatch.setattr("skport.client.SkportAPI", create_api)
    config = ClientConfig(lang=Language.EN)
    client = SkportClient(tokens=["local-test-token"], config=config, lang="ja-JP")
    assert captured["config"].lang == Language.JA
    assert config.lang == Language.EN
    await client.warm()
    api.warm.assert_awaited_once()
    await client.close()
    await client.close()
    api.close.assert_awaited_once()


def test_constructor_rejects_ambiguous_api_ownership(api):
    with pytest.raises(ConfigError):
        SkportClient(api=api, tokens=[])
    with pytest.raises(ConfigError):
        SkportClient(api=api, lang="ja")
    with pytest.raises(ConfigError):
        SkportClient()


@pytest.mark.asyncio
async def test_custom_game_registers_without_enum_or_transport_changes(api):

    class FutureGame:
        game = "future-game"

        def __init__(self, shared_api):
            self.api = shared_api
            self.closed = False

        async def close(self):
            self.closed = True

    client = SkportClient(api=api)
    client.registry.register("future-game", FutureGame)
    custom = client.game("future-game")
    assert custom.api is api
    assert custom is client.game("FUTURE-GAME")
    assert client.registry.names == ("endfield", "future-game")
    await client.close()
    assert custom.closed
    api.close.assert_not_awaited()


def test_registry_does_not_orphan_an_active_client(api):
    registry = GameRegistry()
    registry.register("endfield", EndfieldClient)
    registry.create("endfield", api)
    with pytest.raises(ConfigError, match="active"):
        registry.register("endfield", EndfieldClient, replace=True)
    with pytest.raises(ConfigError, match="Unsupported"):
        registry.create("unknown", api)


@pytest.mark.asyncio
async def test_characters_keep_roster_and_showcase_order_distinct(api):
    client = EndfieldClient(api)
    roster = await client.characters(skport_id="social", raw=True)
    showcase = await client.characters(skport_id="social", showcase_only=True, raw=True)
    assert [char["id"] for char in roster] == ["first", "second", "third"]
    assert [char["id"] for char in showcase] == ["third", "first"]
    assert roster[0]["futureField"] == 7


@pytest.mark.asyncio
async def test_direct_character_id_skips_card_and_keeps_unknown_fields(api):
    result = await EndfieldClient(api).character(skport_id="social", char_id="opaque", lang="ko", raw=True)
    assert result == {"id": "full", "extraField": True}
    api.endfield.detail.assert_not_awaited()
    api.endfield.character.assert_awaited_once_with(
        Target("social", "role", "2"), char_id="opaque", lang="ko"
    )


@pytest.mark.asyncio
async def test_name_selection_normalizes_unicode_and_index_is_explicit(api):
    client = EndfieldClient(api)
    result = await client.character(skport_id="social", name=" ＥＸＡＭＰＬＥ ", full=False, raw=True)
    assert result["id"] == "first"
    result = await client.character(skport_id="social", index=0, showcase_only=True, full=False, raw=True)
    assert result["id"] == "third"
    with pytest.raises(TargetNotFound):
        await client.character(skport_id="social", index=-1, full=False, raw=True)
    with pytest.raises(TargetNotFound):
        await client.character(skport_id="social", name="1", full=False, raw=True)


@pytest.mark.asyncio
async def test_ambiguous_name_requires_id(api):
    api.endfield.detail.return_value["detail"]["chars"][1]["charData"]["name"] = "EXAMPLE"
    with pytest.raises(ConfigError, match="multiple"):
        await EndfieldClient(api).character(skport_id="social", name="Example", full=False, raw=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("selectors", [{}, {"char_id": "x", "index": 0}, {"char_id": ""}])
async def test_selector_errors_precede_network(api, selectors):
    with pytest.raises(ConfigError):
        await EndfieldClient(api).character(skport_id="social", **selectors, raw=True)
    api.endfield.resolve_target.assert_not_awaited()


@pytest.mark.asyncio
async def test_owner_action_forwards_explicit_token(api):
    result = await EndfieldClient(api).check_in(token="owner-test-token", role="3_role_2", lang="ja")
    assert result == {"awards": []}
    api.endfield.check_in.assert_awaited_once_with(token="owner-test-token", role="3_role_2", lang="ja")
