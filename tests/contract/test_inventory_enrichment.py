"""Protect inventory identity, quantities, and display attribution during enrichment."""

from unittest.mock import AsyncMock

import pytest

from skport import SkportClient
from skport.config import ImageSource
from skport.errors import NetworkError
from skport.games.endfield.clean.inventory import enrich_inventory, inventory, inventory_wiki_ids
from skport.games.endfield.identity import Role
from skport.games.endfield.models.images import ImageLinks, SemanticLabel
from skport.games.endfield.models.wiki import WikiSummary

PREFERRED = ImageSource.SKPORT


def test_inventory_enrichment_joins_explicit_and_family_scoped_ids() -> None:
    original = inventory(
        {
            "userGameData": {
                "roleId": "owner-role",
                "serverId": "2",
                "userChars": {"operator": {"owned": True, "level": 30}},
                "userWeapons": {"shared-id": {"owned": True, "name": "Direct weapon name"}},
                "userEquips": {"shared-id": {"ownedCount": 0}, "unmatched": {"ownedCount": 2}},
                "userTacticalItems": {"tactical": {"ownedCount": 1}},
            }
        },
        PREFERRED,
        lang="ja",
    )
    owner_card = {
        "detail": {
            "base": {"roleId": "owner-role"},
            "chars": [
                {
                    "id": "operator",
                    "wikiItemId": "1993",
                    "charData": {"id": "different-nested-id", "name": "Card operator"},
                    "bodyEquip": {"equipId": "shared-id", "equipData": {"name": "Card gear"}},
                    "tacticalItem": {
                        "tacticalItemId": "tactical",
                        "tacticalItemData": {"name": "Card tactical"},
                    },
                }
            ],
        }
    }
    catalog = [
        WikiSummary(
            id="432",
            name="Wiki weapon",
            related_game_id="shared-id",
            locale="ja",
            category=SemanticLabel(key="2"),
            icon=ImageLinks(skport="https://example.test/weapon.png"),
        )
    ]
    summaries = {
        "1993": WikiSummary(
            id="1993",
            name="Wiki operator",
            category=SemanticLabel(key="1"),
            locale="ja",
        )
    }

    assert inventory_wiki_ids(original, owner_card) == {"1993"}
    enriched = enrich_inventory(
        original, PREFERRED, lang="ja", owner_card=owner_card, catalog=catalog, summaries=summaries
    )

    operator = enriched.operators["operator"]
    assert (operator.wiki_item_id, operator.name, operator.level, operator.count) == (
        "1993",
        "Wiki operator",
        30,
        None,
    )
    assert operator.name_source is not None and operator.name_source.source == "wiki_batch"
    assert operator.wiki_item_source is not None and operator.wiki_item_source.source == "owner_card"
    weapon = enriched.weapons["shared-id"]
    assert (weapon.wiki_item_id, weapon.name, weapon.count) == ("432", "Direct weapon name", None)
    assert weapon.name_source is not None and weapon.name_source.source == "inventory"
    assert weapon.icon.url == "https://example.test/weapon.png"
    assert weapon.icon_source is not None and (weapon.icon_source.source, weapon.icon_source.locale) == (
        "wiki_catalog",
        "ja",
    )
    gear = enriched.equipment["shared-id"]
    assert (gear.wiki_item_id, gear.name, gear.owned, gear.count) == (None, "Card gear", False, 0)
    assert not enriched.equipment["unmatched"].name
    assert enriched.tactical_items["tactical"].name == "Card tactical"
    assert not enriched.issues
    assert not original.operators["operator"].name


def test_inventory_enrichment_keeps_ambiguous_ids_and_wrong_owner_unresolved() -> None:
    original = inventory(
        {
            "userGameData": {
                "roleId": "owner-role",
                "serverId": "2",
                "userWeapons": {"weapon": {"owned": True}},
                "userChars": {"operator": {"owned": False}},
            }
        },
        PREFERRED,
    )
    foreign_card = {
        "detail": {
            "base": {"roleId": "different-role"},
            "chars": [{"id": "operator", "wikiItemId": "1993", "charData": {"name": "Foreign card"}}],
        }
    }
    catalog = [
        WikiSummary(
            id=item_id,
            name="Conflicting weapon",
            related_game_id="weapon",
            category=SemanticLabel(key="2"),
        )
        for item_id in ("1", "2")
    ]

    assert not inventory_wiki_ids(original, foreign_card)
    enriched = enrich_inventory(original, PREFERRED, lang="en", owner_card=foreign_card, catalog=catalog)

    assert enriched.operators["operator"].owned is False and not enriched.operators["operator"].name
    assert enriched.weapons["weapon"].owned is True and enriched.weapons["weapon"].wiki_item_id is None
    assert [issue.code for issue in enriched.issues] == ["inventory_card_invalid", "inventory_wiki_ambiguous"]


async def test_inventory_raw_mode_skips_enrichment(monkeypatch: pytest.MonkeyPatch) -> None:
    response = {"userGameData": {"roleId": "owner-role", "serverId": "2"}, "futureField": True}
    token = "test-owner-token"
    requested = "3_owner-role_2"
    async with SkportClient(tokens=[token]) as client:
        raw = client.endfield.raw
        inventory_read = AsyncMock(return_value=response)
        monkeypatch.setattr(raw, "inventory", inventory_read)
        optional_reads = [AsyncMock() for _ in range(4)]
        for name, method in zip(
            ("role_for", "owned_card", "wiki_catalog", "wiki_items"), optional_reads, strict=True
        ):
            monkeypatch.setattr(raw, name, method)

        result = await client.endfield.inventory(token=token, role=requested, lang="ja-JP", enrich=True)

    assert result is response
    inventory_read.assert_awaited_once_with(token=token, role=requested, lang="ja-JP")
    for optional_read in optional_reads:
        optional_read.assert_not_awaited()


@pytest.mark.parametrize("failure", ["network", "invalid_cover", "batch_network", "batch_invalid_cover"])
async def test_inventory_enrichment_uses_selected_role_and_keeps_data_on_optional_failure(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    token = "test-owner-token"
    owner = Role("owner-role", "2", account_uid="owner-account")
    response = {
        "userGameData": {
            "roleId": owner.role_id,
            "serverId": owner.server_id,
            "userChars": {"operator": {"owned": True, "level": 50}},
            "userWeapons": {"weapon": {"owned": True}},
            "userEquips": {"gear": {"ownedCount": 0}},
        }
    }
    owner_card = {
        "detail": {
            "base": {"roleId": owner.role_id},
            "chars": [
                {
                    "id": "operator",
                    "wikiItemId": "1993",
                    "charData": {"name": "Card operator", "avatarSqUrl": "https://example.test/operator.png"},
                }
            ],
        }
    }
    private_error = NetworkError("diagnostic containing private values")

    async def catalog(*, type_sub_id: int, **_: object) -> dict:
        if type_sub_id == 1:
            return {"catalog": []}
        if failure == "network":
            raise private_error
        return {
            "catalog": [
                {
                    "id": "1",
                    "typeSub": [
                        {
                            "id": "2",
                            "items": [
                                {
                                    "itemId": "432",
                                    "name": "Wiki weapon",
                                    "lang": "ja",
                                    "brief": {
                                        "associate": {"id": "weapon"},
                                        "cover": "/invalid.png"
                                        if failure == "invalid_cover"
                                        else "https://example.test/weapon.png",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        }

    batch = AsyncMock(
        return_value={
            "items": {
                "1993": {
                    "itemId": "1993",
                    "mainTypeId": "1",
                    "subTypeId": "1",
                    "name": "Wiki operator",
                    "lang": "ja",
                    "brief": {
                        "associate": {"id": "operator"},
                        "cover": "/invalid.png" if failure == "batch_invalid_cover" else "",
                    },
                }
            },
            "mainTypes": {"1": {"id": "1"}},
            "subTypes": {"1": {"id": "1", "fatherTypeId": "1"}},
        }
    )
    if failure == "batch_network":
        batch.side_effect = private_error

    async with SkportClient(tokens=[token]) as client:
        raw = client.endfield.raw
        selection = AsyncMock(return_value=owner)
        inventory_read = AsyncMock(return_value=response)
        card_read = AsyncMock(return_value=owner_card)
        monkeypatch.setattr(raw, "role_for", selection)
        monkeypatch.setattr(raw, "inventory", inventory_read)
        monkeypatch.setattr(raw, "owned_card", card_read)
        monkeypatch.setattr(raw, "wiki_catalog", catalog)
        monkeypatch.setattr(raw, "wiki_items", batch)

        result = await client.endfield.inventory(
            token=token,
            role=owner.game_role,
            lang="ja-JP",
            raw=False,
            enrich=True,
        )

    selection.assert_awaited_once_with(token, role=owner.game_role, lang="ja")
    inventory_read.assert_awaited_once_with(token=token, role=owner, lang="ja")
    card_read.assert_awaited_once_with(token=token, role=owner, lang="ja")
    batch.assert_awaited_once()
    assert batch.await_args is not None
    assert batch.await_args.args == (["1993"],)
    assert batch.await_args.kwargs["lang"] == "ja"
    operator = result.operators["operator"]
    batch_failed = failure.startswith("batch_")
    assert (operator.owned, operator.level, operator.count, operator.wiki_item_id) == (True, 50, None, "1993")
    assert operator.name == ("Card operator" if batch_failed else "Wiki operator")
    assert operator.icon.url == "https://example.test/operator.png"
    assert result.weapons["weapon"].owned is True
    assert result.weapons["weapon"].name == ("Wiki weapon" if batch_failed else "")
    assert result.equipment["gear"].count == 0
    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("metadata_lookup_failed", "wiki_batch" if batch_failed else "weapon_catalog")
    ]
    assert "diagnostic containing private values" not in result.model_dump_json()
