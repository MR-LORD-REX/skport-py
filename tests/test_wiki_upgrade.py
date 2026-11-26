"""Upgrade projections from captured operator tables."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skport.config import ImageSource
from skport.games.endfield.clean.wiki import wiki_page
from skport.games.endfield.clean.wiki_upgrade import wiki_upgrade_guide
from skport.games.endfield.models.wiki import WikiPage, WikiSummary
from skport.games.endfield.models.wiki_upgrade import WikiUpgradeTotal

_FIXTURES = Path(__file__).parent / "fixtures" / "skport"


def _captured(lang: str) -> WikiPage:
    capture = _FIXTURES / f"wiki_operator_{lang}.json"
    return wiki_page(json.loads(capture.read_text(encoding="utf-8")), ImageSource.SKPORT)


def _quantities(total: WikiUpgradeTotal) -> dict[str, int | None]:
    return {line.wiki_id: line.quantity for line in total.materials}


def test_level_recipes_reconcile_overview_and_merged_detail_and_hydrate_by_wiki_id() -> None:
    protoprism = WikiSummary(id="109", name="Protoprism")
    guide = wiki_upgrade_guide(_captured("en"), index={protoprism.id: protoprism})
    levels = [step for step in guide.steps if step.kind == "level"]
    first = next(step for step in levels if step.to_level == 20)
    (recipe,) = first.costs
    assert {source.block_id for source in recipe.sources} == {"L8hvsN", "BLbHaj"}
    assert recipe.note == "Auto Fill:"
    assert len({line.wiki_id for line in recipe.materials}) == len(recipe.materials) == 4
    assert all(len(line.sources) == 2 for line in recipe.materials)

    total = guide.total([first.id, *(step.id for step in levels)])
    assert total.complete
    assert len(total.step_ids) == len(levels)
    assert _quantities(total) == {"100": 12, "101": 15, "102": 73, "105": 6, "106": 104, "642": 385420}
    assert "1995" not in guide.material_ids
    rank = next(step for step in guide.steps if step.kind == "skill" and step.rank == 2)
    assert rank.costs[0].materials[0].summary == protoprism
    assert rank.costs[0].materials[1].summary is None
    assert guide.total([rank.id]).complete


def test_skill_forms_retain_their_own_mastery_materials_and_unknown_potential() -> None:
    guide = wiki_upgrade_guide(_captured("en"))
    third = [step for step in guide.steps if step.kind == "skill" and step.mastery and step.rank == 3]
    assert len(third) == 2
    assert len({step.skill_id for step in third}) == 2
    basic, battle = third
    assert _quantities(guide.total([basic.id]))["1289"] == 36
    assert _quantities(guide.total([battle.id]))["103"] == 36
    potential = next(step for step in guide.steps if step.kind == "potential")
    assert potential.label == "Wildness Ignited"
    assert potential.rank == 1
    assert potential.effect
    assert potential.icon.url
    assert potential.cost_status == "unknown"
    total = guide.total([basic.id, potential.id])
    assert not total.complete
    assert total.unpriced_step_ids == [potential.id]
    assert _quantities(total)["642"] == 65000


def test_disagreeing_level_recipes_require_a_selection() -> None:
    page = _captured("en")
    widget = next(section for section in page.sections if section.title == "Level Up")
    table = next(block for block in widget.entries[1].blocks if block.kind == "table")
    detail_cell = table.rows[1][2]
    assert detail_cell is not None
    detail_cell.item_refs[0].count = 7

    guide = wiki_upgrade_guide(page)
    detail = next(step for step in guide.steps if step.to_level == 20)
    assert detail.cost_status == "alternative"
    assert len(detail.costs) == 2
    assert not guide.total([detail.id]).complete
    assert not guide.total([detail.id]).materials
    selected = guide.total([detail.id], cost_choices={detail.id: 1})
    assert selected.complete
    assert _quantities(selected)["100"] == 7
    with pytest.raises(ValueError, match="Unknown wiki upgrade step"):
        guide.total(["missing"])


def test_a_merged_price_across_skill_ranks_is_unallocated() -> None:
    page = _captured("en")
    widget = next(section for section in page.sections if section.title == "Combat Skills")
    table = next(block for block in widget.entries[0].blocks if block.kind == "table")
    prices = table.rows[-1]
    shared = prices[2]
    assert shared is not None
    shared.column_span = 2
    prices[3] = None

    guide = wiki_upgrade_guide(page)
    ranked = [step for step in guide.steps if step.skill_kind == "Basic Attack" and step.rank in {2, 3}
              and not step.mastery]
    assert len(ranked) == 2
    assert all(step.cost_status == "partial" for step in ranked)
    assert all(step.costs[0].materials for step in ranked)
    total = guide.total(step.id for step in ranked)
    assert not total.complete
    assert not total.materials


def test_missing_groups_remain_explicit_for_partial_localization() -> None:
    guide = wiki_upgrade_guide(_captured("ja"))
    assert guide.summary.locale == "ja"
    assert not guide.steps
    assert not guide.material_ids
    assert guide.missing_groups == ["level", "promotion", "outfitting", "talent", "skill", "potential"]
