"""Shared headings and cell traversal for published wiki progression tables."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator

from skport.errors import ConfigError
from skport.games.endfield.models.wiki import WikiBlock, WikiPage, WikiTableCell

LEVEL_SECTIONS = frozenset({"level up", "레벨 증가", "レベルアップ"})
SKILL_SECTIONS = frozenset({"combat skills", "전투 스킬", "戦闘スキル"})
COST_LABELS = frozenset({"cost", "재료 소모", "アイテム消費"})

_LEVEL = re.compile(r"lv\.?\s*([1-9][0-9]*)")
_SKILL_RANK = re.compile(r"rank\s*([1-9][0-9]*)")
_MASTERY = re.compile(r"(?:mastery|마스터리|スキル特化)\s*([1-3]|i{1,3})")


def label(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def level_number(text: str) -> int | None:
    match = _LEVEL.fullmatch(label(text))
    return int(match[1]) if match else None


def skill_rank(text: str) -> tuple[int, bool] | None:
    heading = label(text)
    if rank := _SKILL_RANK.fullmatch(heading):
        return int(rank[1]), False
    if mastery := _MASTERY.fullmatch(heading):
        number = mastery[1]
        return (len(number) if number.startswith("i") else int(number)), True
    return None


def walk(blocks: list[WikiBlock]) -> Iterator[WikiBlock]:
    for block in blocks:
        yield from block.walk()


def cell_text(cell: WikiTableCell | None) -> str:
    return cell.text if cell else ""


def require_operator(page: WikiPage) -> None:
    if page.summary.category.key != "1" or page.summary.main_type_id not in {None, "1"}:
        raise ConfigError("wiki article is outside the Operators category")
