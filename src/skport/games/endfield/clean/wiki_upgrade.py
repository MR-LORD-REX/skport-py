"""Project the published operator progression tables into selectable upgrade steps."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Set
from typing import Literal

from skport.games.endfield.clean.wiki_tables import (
    COST_LABELS,
    LEVEL_SECTIONS,
    SKILL_SECTIONS,
    cell_text,
    level_number,
    require_operator,
    skill_rank,
    walk,
)
from skport.games.endfield.clean.wiki_tables import label as normalize_label
from skport.games.endfield.models.base import ModelIssue
from skport.games.endfield.models.images import ImageLinks
from skport.games.endfield.models.wiki import (
    WikiBlock,
    WikiCellSource,
    WikiEntry,
    WikiPage,
    WikiSection,
    WikiSummary,
    WikiTableCell,
)
from skport.games.endfield.models.wiki_upgrade import (
    WikiCostStatus,
    WikiMaterialAmount,
    WikiUpgradeCost,
    WikiUpgradeGuide,
    WikiUpgradeKind,
    WikiUpgradeStep,
)

_SECTIONS = {
    "level": LEVEL_SECTIONS,
    "skill": SKILL_SECTIONS,
    "talent": {"talent nodes", "재능 배열", "素質・配属スキル"},
    "elite": {"elite", "정예화", "昇進"},
    "potential": {"potential phases", "잠재능력 단계", "潜在解放"},
}
_SECTION_KIND = {label: kind for kind, labels in _SECTIONS.items() for label in labels}
_GROUPS: tuple[WikiUpgradeKind, ...] = ("level", "promotion", "outfitting", "talent", "skill", "potential")
_REQUIREMENTS = {"requirements", "활성화 조건", "解放条件"}
_EFFECT = {"talent effect", "advancement effect", "after activation", "활성화 후", "素質効果", "解放後"}
_TRUST = {"trust", "신뢰도", "信頼度"}
_NO_COST = {"none", "-"}
_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4}
_LEVEL = re.compile(r"\blv\.?\s*([1-9][0-9]*)")
_ELITE = re.compile(r"(promotion|outfitting|정예화|장비 조합|昇進|装備適正)[\s・]+(iv|i{1,3})")
_PROMOTION = {"promotion", "정예화", "昇進"}
_CAP = re.compile(r"(?:level cap to\s+|레벨 최대치\s*|レベル上限が\s*)([1-9][0-9]*)")
_POTENTIAL = re.compile(r"(?:potential|잠재능력)\s+0*([1-9][0-9]*)\s*$", re.IGNORECASE)


def _icon(cell: WikiTableCell | None) -> ImageLinks:
    if cell is None:
        return ImageLinks()
    return next((block.image for block in walk(cell.blocks) if block.image.url), ImageLinks())


def _grid(table: WikiBlock) -> list[list[WikiTableCell | None]]:
    grid = [row.copy() for row in table.rows]
    for row_index, row in enumerate(table.rows):
        for column_index, cell in enumerate(row):
            if cell is None or cell.row_span == cell.column_span == 1:
                continue
            for target in grid[row_index:row_index + cell.row_span]:
                for column in range(column_index, min(len(target), column_index + cell.column_span)):
                    if target[column] is None:
                        target[column] = cell
    return grid


def _cost(
    cell: WikiTableCell | None,
    source: WikiCellSource,
    index: Mapping[str, WikiSummary],
    *,
    shared: bool = False,
) -> WikiUpgradeCost:
    if cell is None:
        return WikiUpgradeCost(sources=[source])
    source = source.model_copy(update={"row_id": cell.row_id, "column_id": cell.column_id})
    materials = [
        WikiMaterialAmount(wiki_id=ref.id, quantity=ref.count, summary=index.get(ref.id), sources=[source])
        for ref in cell.item_refs
    ]
    notes: list[str] = []
    for block in walk(cell.blocks):
        if block.kind != "text":
            continue
        note = "".join(run.text for run in block.runs if run.kind != "entry") if block.runs else block.text
        if note.strip() and (block.runs or not block.item_refs):
            notes.append(note.strip())

    note = "\n".join(notes)
    status: WikiCostStatus = "unknown"
    if materials:
        status = "partial" if shared or any(material.quantity is None for material in materials) else "known"
    elif normalize_label(note) in _NO_COST:
        status = "none"
    return WikiUpgradeCost(status=status, materials=materials, sources=[source], note=note, shared=shared)


def _column(headers: list[str], aliases: Set[str]) -> int | None:
    return next((position for position, label in enumerate(headers) if label in aliases), None)


def _number(text: str, pattern: re.Pattern[str]) -> int | None:
    match = pattern.search(normalize_label(text))
    return int(match[1]) if match else None


def _origin(source: WikiCellSource, cell: WikiTableCell | None) -> WikiCellSource:
    return source.model_copy(update={"row_id": cell.row_id, "column_id": cell.column_id}) if cell else source


def _level_steps(
    entry: WikiEntry,
    table: WikiBlock,
    source: WikiCellSource,
    index: Mapping[str, WikiSummary],
) -> Iterator[WikiUpgradeStep]:
    rows = _grid(table)
    headings = rows[0]
    stats_header = [normalize_label(cell_text(cell)) for cell in headings]
    level_cost_col = _column(stats_header, COST_LABELS)
    if level_cost_col is not None and (milestone := level_number(entry.name)) is not None:
        scope = _origin(source, headings[level_cost_col])
        origins = {
            (cell.row_id, cell.column_id): cell
            for row in rows[1:]
            if (cell := row[level_cost_col]) is not None
        }
        costs = [_cost(cell, scope, index) for cell in origins.values()]
        yield WikiUpgradeStep(
            id=f"level:{milestone}", kind="level", label=entry.name, source=scope,
            to_level=milestone, costs=costs or [_cost(None, scope, index)],
        )
        return

    price_row = next((row for row in rows[1:] if normalize_label(cell_text(row[0])) in COST_LABELS), None)
    for column, heading in enumerate(headings):
        milestone = level_number(stats_header[column])
        if milestone is None:
            continue
        cost_cell = price_row[column] if price_row is not None else None
        scope = _origin(source, heading)
        yield WikiUpgradeStep(
            id=f"level:{milestone}", kind="level", label=cell_text(heading), source=scope,
            to_level=milestone,
            costs=[_cost(cost_cell, scope, index, shared=bool(cost_cell and cost_cell.column_span > 1))],
        )


def _skill_steps(
    entry: WikiEntry,
    table: WikiBlock,
    source: WikiCellSource,
    index: Mapping[str, WikiSummary],
) -> Iterator[WikiUpgradeStep]:
    rows = _grid(table)
    price_row = next((row for row in rows[1:] if normalize_label(cell_text(row[0])) in COST_LABELS), None)
    for column, heading in enumerate(rows[0]):
        label = cell_text(heading)
        rank = skill_rank(label)
        if rank is None:
            continue
        number, mastery = rank
        scope = _origin(source, heading)
        price = price_row[column] if price_row is not None else None
        yield WikiUpgradeStep(
            id=f"skill:{source.section_id}:{entry.id}:{table.id}:{scope.column_id}",
            kind="skill", label=label, source=scope, icon=entry.icon, rank=number,
            mastery=mastery, skill_id=entry.id, skill_name=entry.name, skill_kind=entry.kind,
            costs=[_cost(price, scope, index, shared=bool(price and price.column_span > 1))],
        )


def _node_steps(
    table: WikiBlock,
    source: WikiCellSource,
    index: Mapping[str, WikiSummary],
    category: Literal["talent", "elite"],
) -> Iterator[WikiUpgradeStep]:
    rows = _grid(table)
    headings = [normalize_label(cell_text(cell)) for cell in rows[0]]
    cost_column = _column(headings, COST_LABELS)
    effect_column = _column(headings, _EFFECT)
    requirement_columns = [position for position, label in enumerate(headings) if label in _REQUIREMENTS]
    if effect_column is None and cost_column is None:
        return
    for row in rows[1:]:
        label = cell_text(row[0])
        normalized = normalize_label(label)
        if not normalized or normalized in _TRUST:
            continue
        phase = _ELITE.fullmatch(normalized) if category == "elite" else None
        if category == "elite" and phase is None:
            continue
        kind: WikiUpgradeKind = "talent"
        if phase is not None:
            kind = "promotion" if phase[1] in _PROMOTION else "outfitting"
        scope = _origin(source, row[0])
        price = row[cost_column] if cost_column is not None else None
        requirements = list(dict.fromkeys(
            value for column in requirement_columns if (value := cell_text(row[column]))
        ))
        effect = cell_text(row[effect_column]) if effect_column is not None else ""
        yield WikiUpgradeStep(
            id=f"{kind}:{source.section_id}:{source.entry_id}:{table.id}:{scope.row_id}",
            kind=kind, label=label, source=scope, effect=effect, requirements=requirements, icon=_icon(row[0]),
            rank=_ROMAN[phase[2]] if phase else None,
            from_level=_number("\n".join(requirements), _LEVEL) if kind == "promotion" else None,
            to_level=_number(effect, _CAP) if kind == "promotion" else None,
            costs=[_cost(price, scope, index, shared=bool(price and price.row_span > 1))],
        )


def _potential_steps(table: WikiBlock, source: WikiCellSource) -> Iterator[WikiUpgradeStep]:
    for row in table.rows:
        if len(row) < 3:
            continue
        display = cell_text(row[1])
        phase = _POTENTIAL.search(display)
        if phase is None:
            continue
        scope = _origin(source, row[1])
        yield WikiUpgradeStep(
            id=f"potential:{source.section_id}:{source.entry_id}:{table.id}:{scope.row_id}",
            kind="potential", label=display[:phase.start()].strip() or display, source=scope,
            effect=cell_text(row[2]), icon=_icon(row[0]), rank=int(phase[1]), costs=[_cost(None, scope, {})],
        )


def _deduplicate_costs(costs: list[WikiUpgradeCost]) -> list[WikiUpgradeCost]:
    options: dict[tuple[object, ...], WikiUpgradeCost] = {}
    for cost in costs:
        recipe = tuple(sorted((line.wiki_id, line.quantity if line.quantity is not None else -1)
                              for line in cost.materials))
        key = (cost.status, cost.shared, recipe, cost.note if cost.status == "unknown" else "")
        previous = options.get(key)
        if previous is None:
            options[key] = cost
            continue
        previous.sources.extend(source for source in cost.sources if source not in previous.sources)
        previous.note = previous.note or cost.note
        for line in previous.materials:
            line.sources.extend(source for source in cost.sources if source not in line.sources)
    return list(options.values())


def _section_steps(
    page: WikiPage,
    section: WikiSection,
    index: Mapping[str, WikiSummary],
) -> Iterator[WikiUpgradeStep]:
    kind = _SECTION_KIND.get(normalize_label(section.title))
    if kind is None:
        return
    for entry in section.entries:
        for table in entry.blocks:
            if table.kind != "table" or not table.rows or not table.rows[0]:
                continue
            source = WikiCellSource(
                article_id=page.summary.id, locale=page.summary.locale, section_id=section.id,
                entry_id=entry.id, block_id=table.id,
            )
            if kind == "level":
                yield from _level_steps(entry, table, source, index)
            elif kind == "skill":
                yield from _skill_steps(entry, table, source, index)
            elif kind == "talent":
                yield from _node_steps(table, source, index, "talent")
            elif kind == "elite":
                yield from _node_steps(table, source, index, "elite")
            elif kind == "potential":
                yield from _potential_steps(table, source)


def wiki_upgrade_guide(
    page: WikiPage, *, index: Mapping[str, WikiSummary] | None = None,
) -> WikiUpgradeGuide:
    """Extract supported upgrade rows while retaining their published source cells."""
    require_operator(page)
    material_index = index or {}
    steps: dict[str, WikiUpgradeStep] = {}
    issues = list(page.issues)
    for section in page.sections:
        for step in _section_steps(page, section, material_index):
            if step.id in steps:
                steps[step.id].costs.extend(step.costs)
            else:
                steps[step.id] = step

    for step in steps.values():
        step.costs = _deduplicate_costs(step.costs)
        if len(step.costs) > 1:
            issues.append(ModelIssue(
                code="wiki_upgrade_cost_alternatives",
                message="The article gives different cost observations for an upgrade step",
                path=step.id,
            ))
    kinds = {step.kind for step in steps.values()}
    return WikiUpgradeGuide(
        summary=page.summary, steps=list(steps.values()),
        missing_groups=[kind for kind in _GROUPS if kind not in kinds], issues=issues,
    )
