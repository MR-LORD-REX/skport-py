"""Contracts for the captured SKPORT wiki and public banner responses."""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any, Literal

import pytest

from skport.config import ImageSource
from skport.errors import DecodeError
from skport.games.endfield.clean.wiki import banners, wiki_catalog, wiki_page

_FIXTURES = Path(__file__).parent / "fixtures" / "skport"
_SOURCE = ImageSource.SKPORT


def _captured(name: str) -> Any:
    return json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_wiki_catalog_connects_article_and_game_ids() -> None:
    catalog = wiki_catalog(_captured("wiki_operators"), _SOURCE)
    page = wiki_page(_captured("wiki_operator_en"), _SOURCE)
    summary = next(row for row in catalog if row.id == page.summary.id)
    assert summary.name == page.summary.name == "Kay"
    assert summary.related_game_id == page.summary.related_game_id
    assert summary.related_game_id and summary.related_game_id != summary.id
    assert summary.category.key == "1"
    assert summary.category.name == "Operators"
    assert summary.icon.url
    assert summary.locale == "en"
    assert {tag.name for tag in summary.tags} >= {"6★", "Nature"}
    assert "Young in age" in summary.description


def test_wiki_operator_exposes_readable_content_and_material_links() -> None:
    page = wiki_page(_captured("wiki_operator_en"), _SOURCE)
    assert page.quote.startswith("All the way from there to here")
    assert page.bio.startswith("Young in age")
    assert page.illustration.url
    assert {field.label: field.value for field in page.info_fields}["Codename"] == "Kay"
    assert page.skill_entries[0].name == "Wild Wacky-Whack"
    assert page.skill_entries[0].kind == "Basic Attack"
    assert page.skill_entries[0].description
    assert page.skill_entries[0].blocks
    assert page.lore[0].text
    recommendation = next(section for section in page.sections if section.title == "Game Recommendation")
    (entry,) = recommendation.entries
    table = next(block for block in entry.blocks if block.kind == "table")
    refs = [ref for row in table.rows for cell in row if cell for block in cell.blocks for ref in block.item_refs]
    assert refs[0].id == recommendation.items[0].id
    assert refs[0].display_type
    assert entry.text
    assert not page.issues


def test_wiki_expands_only_links_in_the_supplied_index() -> None:
    summary = next(row for row in wiki_catalog(_captured("wiki_weapons"), _SOURCE) if row.name == "Sweet Deal")
    page = wiki_page(_captured("wiki_operator_en"), _SOURCE, index={summary.id: summary})
    section = next(section for section in page.sections if section.title == "Game Recommendation")
    table = next(block for block in section.entries[0].blocks if block.kind == "table")
    refs = [ref for row in table.rows for cell in row if cell for block in cell.blocks for ref in block.item_refs]
    named = next(ref for ref in refs if ref.id == summary.id)
    assert named.item and named.item.name == summary.name
    assert summary.name in section.text
    assert any(ref.id != summary.id and ref.item is None for ref in refs)


def test_wiki_localized_sections_and_empty_weapon_article() -> None:
    localized = wiki_page(_captured("wiki_operator_ja"), _SOURCE)
    assert localized.summary.name == "ケーちゃん"
    assert localized.summary.locale == "ja"
    assert localized.quote.startswith("ここからここまで")
    assert localized.sections[0].title == "基本情報"
    assert localized.sections[0].fields[0].label == "コードネーム"
    assert any(
        block.kind == "video" and block.url
        for section in localized.sections for entry in section.entries for block in entry.blocks
    )
    assert not localized.issues

    weapon = wiki_page(_captured("wiki_weapon_en"), _SOURCE)
    summary = next(
        row for row in wiki_catalog(_captured("wiki_weapons"), _SOURCE) if row.id == weapon.summary.id
    )
    assert weapon.summary.category.key == summary.category.key == "2"
    assert weapon.summary.name == summary.name == "Star of Tomorrow"
    assert weapon.sections == []
    assert weapon.summary.icon.url


def test_wiki_preserves_unknown_blocks_and_reports_missing_and_cyclic_references() -> None:
    payload = {"item": {
        "itemId": "test-article",
        "document": {
            "chapterGroup": [{"id": "0", "title": "Overview", "widgets": [{"id": "widget"}]}],
            "widgetCommonMap": {
                "widget": {
                    "type": "common",
                    "tabDataMap": {
                        "default": {"intro": {"description": "missing-doc"}, "content": "test-doc"},
                    },
                },
            },
            "documentMap": {
                "test-doc": {
                    "blockIds": ["box"],
                    "blockMap": {
                        "box": {
                            "kind": "futureBox",
                            "futureBox": {"look": "important", "childIds": ["box", "absent", "body"]},
                        },
                        "body": {
                            "kind": "text",
                            "text": {"inlineElements": [{"kind": "text", "text": {"text": "Line 1\nLine 2"}}]},
                        },
                    },
                },
            },
        },
    }}
    page = wiki_page(payload, _SOURCE)
    (issue_doc, issue_cycle, issue_block) = page.issues
    assert issue_doc.code == "wiki_document_missing"
    assert issue_cycle.code == "wiki_block_nesting"
    assert issue_block.code == "wiki_block_missing"
    (block,) = page.sections[0].entries[0].blocks
    assert block.kind == "unknown"
    assert block.source_type == "futureBox"
    assert block.metadata["look"] == "important"
    assert block.text == "Line 1\nLine 2"


@pytest.mark.parametrize(("fixture", "kind"), [("char_banners", "character"), ("weapon_banners", "weapon")])
def test_banners_preserve_display_metadata_and_regional_pool_windows(
    fixture: str, kind: Literal["character", "weapon"],
) -> None:
    result = banners(_captured(fixture), kind=kind, preferred=_SOURCE)
    first = result[0]
    assert first.kind == kind
    assert first.id and first.name and first.starts_at and first.ends_at
    assert first.starts_at.tzinfo == UTC
    assert first.starts_at < first.ends_at
    assert [window.region for window in first.windows] == ["default", "europe"]
    assert first.windows[0].ends_at and first.windows[0].ends_at.tzinfo == UTC
    item = first.items[0]
    assert item.link and "gameEntryId=" in item.link
    assert item.icon.url and item.rarity == 6
    assert item.dot_type == "label_type_up"
    assert item.name == ""


def test_wiki_and_banners_reject_unexpected_top_level_payloads() -> None:
    with pytest.raises(DecodeError, match="wiki catalog did not contain a list"):
        wiki_catalog({"catalog": {}}, _SOURCE)
    with pytest.raises(DecodeError, match="itemId"):
        wiki_page({"item": {}}, _SOURCE)
    with pytest.raises(DecodeError, match="banner response did not contain a list"):
        banners({}, kind="character", preferred=_SOURCE)
