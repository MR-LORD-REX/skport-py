"""Inputs and diagnostic outputs shared by resolution and calculation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ResolvedEquipment:
    """An identified gear item with the wire enhancement slots preserved."""

    slot: str
    item_id: int
    record: dict[str, Any]
    enhancements: dict[str, int]
    modifier_slots: tuple[int, ...]
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResolvedCharacter:
    """Canonical calculation inputs alongside the original SKPORT character."""

    avatar_id: int
    avatar: dict[str, Any]
    raw: dict[str, Any]
    weapon_id: int | None = None
    weapon: dict[str, Any] | None = None
    equipment: tuple[ResolvedEquipment, ...] = ()
    weapon_skill_levels: tuple[int, ...] = ()
    gem_template_id: int | None = None
    gem_terms: tuple[tuple[int, int], ...] = ()
    revision: str = ""
    warnings: tuple[str, ...] = ()
    display_avatar_id: int | None = None
    attribute_nodes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Contribution:
    """A single source modifier before final aggregation and rounding."""

    stat_id: int
    value: float
    formula: str
    source: str
    original_stat_id: int | None = None


@dataclass(frozen=True, slots=True)
class CalculationResult:
    """Generic stat values, units and enough evidence to audit their origins."""

    values: dict[int, float | int]
    units: dict[int, str]
    contributions: tuple[Contribution, ...]
    main_attribute: int
    sub_attribute: int
    warnings: tuple[str, ...] = ()
