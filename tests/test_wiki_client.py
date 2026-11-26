"""Client contracts for wiki discovery, locale handling, and card preparation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from skport import SkportAPI, WikiNotFound
from skport.api.request import query_pairs
from skport.config import ClientConfig, ImageSource
from skport.errors import DecodeError, NetworkError
from skport.games.endfield import EndfieldClient, endpoints
from skport.games.endfield.clean.wiki import wiki_page
from skport.games.endfield.clean.wiki_operator import wiki_operator

_FIXTURES = Path(__file__).parent / "fixtures" / "skport"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class WikiAPI(SkportAPI):
    def __init__(self, data: dict[str, Any]) -> None:
        self.config = ClientConfig()
        self._credential_cache = {}
        self.data = data
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        assert method == "GET"
        assert not kwargs.get("token") and not kwargs.get("role")
        self.calls.append((path, kwargs))
        result = self.data[path]
        if callable(result):
            return result(**kwargs)
        if isinstance(result, Exception):
            raise result
        return result


def _item(item_id: str, name: str, sub_id: str = "1", lang: str = "en") -> dict[str, Any]:
    return {"itemId": item_id, "name": name, "lang": lang, "mainTypeId": "1", "subTypeId": sub_id}


async def test_discovery_and_search_preserve_category_identity() -> None:
    catalog = _fixture("wiki_operators")
    sub = catalog["catalog"][0]["typeSub"][0]
    kay = next(row for row in sub["items"] if row["itemId"] == "1993")
    operator = dict(kay, mainType={"id": "1"}, subType={"id": "1", "name": "Operators"})
    guide = dict(kay, itemId="2000", mainType={"id": "2"}, subType={"id": "10"})
    api = WikiAPI({endpoints.WIKI_CATALOG: catalog, endpoints.WIKI_SEARCH: {"items": [operator, guide]}})
    client = EndfieldClient(api)

    tree = await client.wiki_categories(ttl=0)
    assert query_pairs(api.calls[0][1]["params"]) == []
    assert api.calls[0][1]["ttl"] == 0
    category = tree.categories[0].subcategories[0]
    assert category.key == "1" and category.filters
    index = await client.wiki_index(categories=[(1, 1)])
    item = index.items["1993"]
    assert item.association and item.association.kind == "char"
    assert item.caption and any(tag.value == "rarity_6" for tag in item.facets)
    assert index.by_game_id(item.association.game_id, type_sub_id=1) == [item]
    search = await client.wiki_search(" Kay ", category=(1, 1))
    assert [item.id for item in search] == ["1993"]
    assert api.calls[-1][1]["params"] == {"keyword": "Kay"}


async def test_batches_send_repeated_ids_and_identify_omissions() -> None:
    def batch(**kwargs: Any) -> dict[str, Any]:
        keys = kwargs["params"]["ids"]
        return {
            "items": {k: _item(k, "Localized", lang="ja") for k in keys if k != "31"},
            "mainTypes": {"1": {"id": "1", "name": "Database"}},
            "subTypes": {"1": {"id": "1", "name": "Operators"}},
        }

    api = WikiAPI({endpoints.WIKI_ITEMS: batch})
    client = EndfieldClient(api)
    result = await client.wiki_items([*range(1, 32), "1"], lang="ja-JP")
    assert len(result.items) == 30
    assert result.locale == result.items["1"].locale == "ja"
    assert result.missing_ids == ["31"]
    assert sorted(len(call[1]["params"]["ids"]) for call in api.calls) == [1, 30]
    assert query_pairs(api.calls[0][1]["params"])[:3] == [("ids", "1"), ("ids", "2"), ("ids", "3")]
    assert all(call[1]["params"]["lang"] == "ja" for call in api.calls)
    assert (await client.wiki_items([])).requested_ids == []
    assert len(api.calls) == 2


async def test_operator_keeps_partial_translation_and_falls_back_for_absent_article() -> None:
    def article(**kwargs: Any) -> dict[str, Any]:
        locale = kwargs["lang"]
        return {"item": None} if locale == "zh-Hans" else _fixture(f"wiki_operator_{locale}")

    api = WikiAPI({endpoints.WIKI_INFO: article})
    client = EndfieldClient(api)
    partial = await client.wiki_operator(1993, lang="ja", fallback_lang="en")
    assert partial.summary.locale == "ja" and not partial.stats and not partial.skills
    with pytest.raises(WikiNotFound):
        await client.wiki_item(1993, lang="zh-Hans")
    info = await client.wiki_operator(1993, lang="zh-Hans", fallback_lang="en")
    assert (info.requested_locale, info.summary.locale) == ("zh-Hans", "en")
    assert info.rarity == 6 and info.element and info.element.value == "char_property_natural"
    assert [snapshot.level for snapshot in info.stats] == [1, 20, 40, 60, 80, 90]
    (strength,) = [value for value in info.stats[-1].values if value.key == "strength"]
    assert strength.value == 171 and strength.source.article_id == "1993"
    assert len(info.skills) == 2 and len(info.skills[0].ranks) == 12
    assert info.skills[0].ranks[0].values[0].unit == "%"
    assert info.skills[0].ranks[-1].mastery
    api.data[endpoints.WIKI_INFO] = {"item": {"itemId": 1993, "document": []}}
    with pytest.raises(DecodeError, match="document"):
        await client.wiki_item(1993)


def test_stats_keep_source_alternatives_when_overview_differs_from_level_tab() -> None:
    page = wiki_page(_fixture("wiki_operator_en"), ImageSource.SKPORT)
    section = next(section for section in page.sections if section.title == "Level Up")
    detail = next(block for block in section.entries[1].blocks if block.kind == "table")
    assert detail.rows[1][1] is not None
    detail.rows[1][1].blocks[0].text = "999"
    info = wiki_operator(page)
    snapshot = next(snapshot for snapshot in info.stats if snapshot.level == 20)
    assert snapshot.values[0].value == 54
    assert snapshot.alternatives["strength"][0].value == 999
    assert snapshot.alternatives["strength"][0].source.entry_id == section.entries[1].id
    assert any(issue.code == "wiki_stat_disagreement" for issue in info.issues)


async def test_optional_banner_and_material_metadata_preserve_core_results() -> None:
    api = WikiAPI({
        endpoints.CHAR_BANNERS: _fixture("char_banners"),
        endpoints.WIKI_INFO: _fixture("wiki_operator_en"),
        endpoints.WIKI_ITEMS: NetworkError("unavailable"),
    })
    client = EndfieldClient(api)
    (banner,) = await client.char_banners(ttl=0)
    assert banner.items[0].wiki_id == "1993" and banner.issues
    assert api.calls[-1][1]["ttl"] == 0
    guide = await client.wiki_upgrade_guide(1993)
    assert any(issue.code == "metadata_lookup_failed" for issue in guide.issues)
    assert guide.total([step.id for step in guide.steps if step.kind == "promotion"]).complete

    api.data[endpoints.WIKI_ITEMS] = {"items": {"1993": _item("1993", "Kay")}, "mainTypes": {}, "subTypes": {}}
    (hydrated,) = await client.char_banners()
    assert hydrated.items[0].name == "Kay"
    assert hydrated.items[0].id == banner.items[0].id
