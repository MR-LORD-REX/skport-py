"""Canonical stat metadata and presentation without magnitude-based units."""

from __future__ import annotations

from typing import Any

from skport.config import ImageSource
from skport.games.endfield.calc.sheet import stat_unit
from skport.games.endfield.calc.types import CalculationResult
from skport.games.endfield.clean.common import image_links
from skport.games.endfield.models.stats import StatBlock, StatContribution, StatModifier, StatUnit, StatValue

STAT_LABELS = {
    1: "HP",
    2: "ATK",
    3: "DEF",
    4: "Physical Damage Taken",
    5: "Heat Damage Taken",
    6: "Electric Damage Taken",
    7: "Cryo Damage Taken",
    9: "Critical Rate",
    10: "Critical Damage",
    15: "Attack Speed",
    17: "Basic Attack Damage",
    26: "Stagger Output",
    28: "Ultimate Damage",
    29: "Treatment Bonus",
    30: "Treatment Received",
    32: "Battle Skill Damage",
    33: "Combo Skill Damage",
    39: "Strength",
    40: "Agility",
    41: "Intellect",
    42: "Will",
    44: "Ultimate Gain",
    47: "Combo Skill Cooldown",
    48: "Nature Damage Taken",
    50: "Physical Damage",
    51: "Heat Damage",
    52: "Electric Damage",
    53: "Cryo Damage",
    54: "Nature Damage",
    55: "Ether Damage",
    60: "Ether Damage Taken",
    61: "Damage Against Staggered",
    87: "Arts Intensity",
}
STAT_ICONS = {
    39: "Str",
    40: "Agi",
    41: "Wisd",
    42: "Will",
    50: "PhysicalDamageIncrease",
    51: "FireDamageIncrease",
    52: "PulseDamageIncrease",
    53: "CrystDamageIncrease",
    54: "NaturalDamageIncrease",
    55: "EtherDamageIncrease",
}
GROUP_LABELS = {
    frozenset({52, 53}): "Cryo & Electric Damage",
    frozenset({51, 54}): "Heat & Nature Damage",
    frozenset({51, 52, 53, 54}): "Arts Damage",
    frozenset({28, 32, 33}): "All Skill Damage",
    frozenset({4, 5, 6, 7, 48, 60}): "Damage Taken",
}


def stat_name(stat_id: int, labels: dict[str, str] | None = None) -> str:
    """Use localized ID metadata when available, retaining unknown properties."""
    return (labels or {}).get(str(stat_id)) or STAT_LABELS.get(stat_id, f"Stat {stat_id}")


def modifier_unit(stat_id: int, formula: str) -> StatUnit:
    """Describe a contribution's unit separately from the final stat's unit."""
    if formula == "BaseMultiplier":
        return StatUnit.FRACTION
    if formula == "BaseFinalMultiplier":
        return StatUnit.FACTOR
    return StatUnit(stat_unit(stat_id))


def stat_modifier(
    stat_id: int | str,
    value: float,
    formula: str,
    avatar: dict[str, Any] | None = None,
) -> StatModifier:
    """Expand main/sub identities while preserving each formula and value."""
    key = int(stat_id)
    if avatar is not None:
        key = {10000: int(avatar["MainAttrId"]), 10001: int(avatar["SubAttrId"])}.get(key, key)
    return StatModifier(id=key, value=value, formula=formula, unit=modifier_unit(key, formula))


def build_stats(
    result: CalculationResult,
    preferred: ImageSource,
    labels: dict[str, str] | None = None,
) -> StatBlock:
    """Build a serializable property dictionary with contribution evidence."""
    values = {}
    for stat_id, amount in result.values.items():
        icon = STAT_ICONS.get(stat_id)
        values[stat_id] = StatValue(
            id=stat_id,
            value=amount,
            unit=StatUnit(result.units[stat_id]),
            name=stat_name(stat_id, labels),
            icon=image_links(enka=f"/ui/ef/attributeicon/{icon}.png" if icon else None, preferred=preferred),
            is_main=stat_id == result.main_attribute,
            is_sub=stat_id == result.sub_attribute,
        )
    contributions = []
    for source in result.contributions:
        parts = source.source.split(":")
        source_id = (
            parts[2] if parts[0] == "equipment" and len(parts) > 2 else parts[1] if len(parts) > 1 else ""
        )
        contributions.append(
            StatContribution(
                stat_id=source.stat_id,
                source=source.source,
                formula=source.formula,
                value=source.value,
                source_id=source_id,
            )
        )
    return StatBlock(
        values=values,
        main_attribute=result.main_attribute,
        sub_attribute=result.sub_attribute,
        contributions=contributions,
    )
