"""Regression tests for published list items, table cells, and inline elements."""

from __future__ import annotations

from typing import Any

from skport.config import ImageSource
from skport.games.endfield.clean.wiki import wiki_material, wiki_page


def _text(*runs: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "text", "text": {"inlineElements": list(runs)}}


def _entry(item_id: str, count: int) -> dict[str, Any]:
    return {"kind": "entry", "entry": {"id": item_id, "count": count}}


def test_material_sources_keep_the_list_order_and_inline_content() -> None:
    page = wiki_page({"item": {
        "itemId": "128",
        "lang": "en",
        "document": {
            "chapterGroup": [{"title": "Item Source", "widgets": [{"id": "source", "title": "//Source"}]}],
            "widgetCommonMap": {
                "source": {
                    "type": "common",
                    "tabList": [{"tabId": "missing", "title": "Missing"}],
                    "tabDataMap": {"default": {"content": "acquisition"}},
                },
            },
            "documentMap": {
                "acquisition": {"blockIds": ["list"], "blockMap": {
                    "list": {"kind": "list", "list": {
                        "id": "list",
                        "kind": "unordered",
                        "itemIds": ["gem", "site"],
                        "itemMap": {
                            "site": {"childIds": ["link"]},
                            "gem": {"childIds": ["intro", "item"]},
                        },
                    }},
                    "link": _text({"kind": "link", "link": {"link": "https://wiki.skport.com", "text": "The Hub"}}),
                    "intro": _text({
                        "kind": "text", "text": {"text": "Rare Gathering Sites"},
                        "bold": True, "color": "light_text_primary",
                    }),
                    "item": _text(_entry("130", 1)),
                }},
            },
        },
    }}, ImageSource.SKPORT)
    material = wiki_material(page)
    (source,) = material.acquisition
    assert [entry.id for entry in source.entries] == ["missing", "default"]
    assert source.entries[1].content_id == "acquisition"
    (listed,) = source.entries[1].blocks
    assert listed.kind == "list" and listed.list_kind == "unordered"
    assert [item.id for item in listed.list_items] == ["gem", "site"]
    first, second = listed.list_items
    assert first.blocks[0].runs[0].bold and first.blocks[0].runs[0].color == "light_text_primary"
    assert second.blocks[0].runs[0].url == "https://wiki.skport.com"
    assert "Rare Gathering Sites" in source.text and "The Hub" in source.text
    assert [item.id for item in source.items] == ["130"]
    assert [issue.code for issue in material.issues] == ["wiki_tab_missing"]


def test_material_recipe_preserves_merged_requirement_and_keeps_inputs_and_outputs() -> None:
    rows = {
        "head": ("Chamber Recipe Unlock Level", "Materials Needed", "Production "),
        "first": ("1", _entry("128", 1), _entry("130", 3)),
        "second": (None, _entry("130", 1), _entry("128", 1)),
    }
    cells = {}
    blocks = {}
    for row_id, values in rows.items():
        for column, value in enumerate(values):
            if value is None:
                continue
            cell_id = f"{row_id}_{column}"
            cells[cell_id] = {"childIds": [cell_id], "rowSpan": "2" if cell_id == "first_0" else "1"}
            run = {"kind": "text", "text": {"text": value}} if isinstance(value, str) else value
            blocks[cell_id] = _text(run)
    blocks["recipe"] = {"kind": "table", "table": {
        "rowIds": list(rows), "columnIds": ["0", "1", "2"], "cellMap": cells,
        "rowHeader": True, "colHeader": False,
    }}
    page = wiki_page({"item": {
        "itemId": "128",
        "lang": "en",
        "document": {
            "chapterGroup": [{
                "title": "Applicable Formulas", "widgets": [{"id": "seeds", "title": "//Seeds Extraction"}],
            }],
            "widgetCommonMap": {"seeds": {"type": "common", "tabDataMap": {"default": {"content": "formulas"}}}},
            "documentMap": {"formulas": {"blockIds": ["recipe"], "blockMap": blocks}},
        },
    }}, ImageSource.SKPORT)
    material = wiki_material(page)
    assert not material.issues
    (table,) = material.recipe_sections[0].entries[0].blocks
    assert table.row_header is True and table.column_header is False
    assert table.row_ids == ["head", "first", "second"]
    origin = table.rows[1][0]
    assert origin is not None and origin.row_id == "first" and origin.column_id == "0" and origin.row_span == 2
    assert table.rows[2][0] is None
    assert [recipe.requirement for recipe in material.recipes] == ["1", "1"]
    assert [recipe.row_id for recipe in material.recipes] == ["first", "second"]
    assert [[(entry.id, entry.count) for entry in recipe.inputs] for recipe in material.recipes] == [
        [("128", 1)], [("130", 1)],
    ]
    assert [[(entry.id, entry.count) for entry in recipe.outputs] for recipe in material.recipes] == [
        [("130", 3)], [("128", 1)],
    ]
