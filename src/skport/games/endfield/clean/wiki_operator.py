"""Extract reference-card fields and source cells from an operator article."""

from __future__ import annotations

import re
from collections.abc import Iterator

from skport.games.endfield.clean.wiki_tables import (
    COST_LABELS,
    LEVEL_SECTIONS,
    SKILL_SECTIONS,
    cell_text,
    label,
    level_number,
    require_operator,
    skill_rank,
    walk,
)
from skport.games.endfield.models.base import ModelIssue
from skport.games.endfield.models.wiki import WikiBlock, WikiCellSource, WikiEntry, WikiPage, WikiSection
from skport.games.endfield.models.wiki_operator import (
    WikiOperatorReference,
    WikiPublishedValue,
    WikiSkillRank,
    WikiSkillReference,
    WikiStatSnapshot,
)

_STATS = {
    "strength": {"strength", "筋力", "힘"},
    "agility": {"agility", "敏捷", "민첩"},
    "intellect": {"intellect", "知性", "지능"},
    "will": {"will", "意志", "의지"},
    "base_atk": {"base atk", "基礎攻撃力", "기초 공격력"},
    "base_hp": {"base hp", "基礎hp", "기초 생명력"},
}
_STAT_KEYS = {name: key for key, names in _STATS.items() for name in names}
_DETAIL_HEADERS = {
    "initial data", "attribute increase", "max data",
    "ステータス", "기본 능력치", "능력치 증가", "최대 레벨 능력치",
}
_RARITY = re.compile(r"rarity_([1-9][0-9]*)")
_MEASUREMENT = re.compile(r"([+\-−]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?)\s*(%|s|초|秒)?")


def _column_values(
    table: WikiBlock,
    column: int,
    source: WikiCellSource,
    *,
    stats: bool,
) -> Iterator[WikiPublishedValue]:
    for row in table.rows[1:]:
        cell = row[column] if column < len(row) else None
        title = cell_text(row[0]) if row else ""
        normalized = label(title)
        key = _STAT_KEYS.get(normalized.partition("(")[0].strip()) if stats else None
        if not cell or not cell.text or not title or normalized in COST_LABELS or (stats and key is None):
            continue
        value, unit = None, None
        if match := _MEASUREMENT.fullmatch(label(cell.text)):
            number = match[1].replace(",", "").replace("−", "-")
            value = float(number) if "." in number else int(number)
            unit = "s" if match[2] in {"초", "秒"} else match[2]
        yield WikiPublishedValue(
            label=title,
            key=key,
            text=cell.text,
            value=value,
            unit=unit,
            source=source.model_copy(update={"row_id": cell.row_id, "column_id": cell.column_id}),
        )


def _source(page: WikiPage, section: WikiSection, entry: WikiEntry, table: WikiBlock) -> WikiCellSource:
    return WikiCellSource(
        article_id=page.summary.id, locale=page.summary.locale, section_id=section.id,
        entry_id=entry.id, block_id=table.id,
    )


def _entry_tables(entry: WikiEntry) -> Iterator[WikiBlock]:
    return (table for table in walk(entry.blocks) if table.kind == "table" and table.rows)


def _stat_snapshots(
    page: WikiPage, sections: list[WikiSection], issues: list[ModelIssue]
) -> list[WikiStatSnapshot]:
    published: dict[int, dict[str, WikiPublishedValue]] = {}
    overview: dict[int, dict[str, WikiPublishedValue]] = {}
    alternatives: dict[int, dict[str, list[WikiPublishedValue]]] = {}
    for section in sections:
        for entry in section.entries:
            for table in _entry_tables(entry):
                source = _source(page, section, entry, table)
                for column, header in enumerate(table.rows[0][1:], start=1):
                    heading = cell_text(header)
                    level = level_number(heading)
                    target = overview
                    if level is None and label(heading) in _DETAIL_HEADERS:
                        level = level_number(entry.title or entry.name)
                        target = published
                    if level is None:
                        continue
                    for stat in _column_values(table, column, source, stats=True):
                        target.setdefault(level, {})[stat.key or stat.label] = stat

    for level, values in overview.items():
        detail = published.setdefault(level, {})
        for key, value in values.items():
            previous = detail.get(key)
            if previous and (
                (previous.value, previous.unit) != (value.value, value.unit)
                or (value.value is None and previous.text != value.text)
            ):
                alternatives.setdefault(level, {}).setdefault(key, []).append(previous)
                issues.append(
                    ModelIssue(
                        code="wiki_stat_disagreement",
                        message="The level overview and level detail show different values",
                        path=f"stats.{level}.{key}",
                    )
                )
            detail[key] = value
    return [
        WikiStatSnapshot(
            level=level, values=list(published[level].values()), alternatives=alternatives.get(level, {})
        )
        for level in sorted(published)
    ]


def _skill_reference(page: WikiPage, section: WikiSection, entry: WikiEntry) -> WikiSkillReference:
    ranks: dict[tuple[int, bool], WikiSkillRank] = {}
    for table in _entry_tables(entry):
        source = _source(page, section, entry, table)
        for column, header in enumerate(table.rows[0][1:], start=1):
            heading = cell_text(header)
            rank = skill_rank(heading)
            if rank is not None:
                parsed = ranks.setdefault(rank, WikiSkillRank(label=heading, rank=rank[0], mastery=rank[1]))
                parsed.values.extend(_column_values(table, column, source, stats=False))
    return WikiSkillReference(
        id=entry.id,
        section_id=section.id,
        name=entry.name or entry.title,
        kind=entry.kind,
        description=entry.description,
        icon=entry.icon,
        intro_blocks=entry.intro_blocks,
        ranks=list(ranks.values()),
    )


def wiki_operator(page: WikiPage, *, requested_locale: str | None = None) -> WikiOperatorReference:
    """Project published attributes and metrics without calculating a player build."""
    require_operator(page)
    issues = page.issues.copy()
    stats = _stat_snapshots(page, [s for s in page.sections if label(s.title) in LEVEL_SECTIONS], issues)
    skills = [
        _skill_reference(page, section, entry)
        for section in page.sections if label(section.title) in SKILL_SECTIONS
        for entry in section.entries
    ]
    if not stats:
        issues.append(ModelIssue(code="wiki_stats_unavailable", message="No recognized level stats", path="stats"))
    if not skills:
        issues.append(ModelIssue(code="wiki_skills_unavailable", message="No recognized combat skills", path="skills"))
    for skill in skills:
        if not skill.ranks:
            issues.append(
                ModelIssue(
                    code="wiki_skill_ranks_unavailable", message="No recognized rank columns",
                    path=f"skills.{skill.section_id}.{skill.id}",
                )
            )
    facets = {tag.group_id: tag for tag in page.summary.facets}
    rarity_tag = facets.get("10000")
    rarity = _RARITY.fullmatch(rarity_tag.value) if rarity_tag else None
    return WikiOperatorReference(
        summary=page.summary,
        requested_locale=requested_locale or page.summary.locale,
        illustration=page.illustration,
        rarity=int(rarity[1]) if rarity else None,
        element=facets.get("10100"),
        profession=facets.get("10200"),
        weapon_type=facets.get("10213"),
        faction=facets.get("10219"),
        quote=page.quote,
        bio=page.bio,
        info_fields=page.info_fields,
        stats=stats,
        skills=skills,
        lore=page.lore,
        issues=issues,
    )
