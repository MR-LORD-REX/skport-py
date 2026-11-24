"""Static Endfield stat calculation from canonical raw Enka tables."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from skport.errors import ConfigError, MappingError
from skport.games.endfield.calc.sheet import StatSheet, stat_unit
from skport.games.endfield.calc.types import CalculationResult, ResolvedCharacter


def _level(value: Any, *, source: str) -> int:
    """Accept integer wire levels without silently truncating invalid inputs."""
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ConfigError("level must be a positive integer", context={"source": source}) from exc
    if isinstance(value, bool) or parsed < 1 or (isinstance(value, float) and value != parsed):
        raise ConfigError("level must be a positive integer", context={"source": source})
    return parsed


def _curve(values: list[Any], level: int, *, source: str) -> float:
    """Select a level curve value while rejecting invalid or stale levels."""
    if isinstance(level, bool) or level < 1 or level > len(values):
        raise ConfigError("level is outside the asset curve", context={"level": level, "source": source})
    return float(values[level - 1])


def _skill(sheet: StatSheet, tables: dict[str, Any], skill_id: int | str, level: int, source: str) -> None:
    """Apply the static properties declared for one effective skill level."""
    if isinstance(level, bool) or not isinstance(level, int) or level < 0:
        raise ConfigError("skill level must be a nonnegative integer", context={"skill_id": skill_id})
    if level == 0:
        return
    skill = tables["skills"].get(str(skill_id))
    if skill is None:
        raise MappingError("weapon or suit skill is missing", context={"skill_id": skill_id})
    for stat_id, prop in skill.get("PropMap", {}).items():
        values = prop["Values"]
        if not values:
            raise MappingError(
                "skill property has no values", context={"skill_id": skill_id, "stat_id": stat_id}
            )
        if len(values) > 1 and level > len(values):
            raise MappingError(
                "skill level is not covered by the cached asset curve",
                context={"skill_id": skill_id, "stat_id": stat_id, "level": level},
            )
        sheet.add(stat_id, float(values[min(level, len(values)) - 1]), prop["Formula"], source=source)


def _passives(sheet: StatSheet, resolved: ResolvedCharacter) -> float:
    """Apply the two known unconditional sheet passives from unlocked nodes."""
    sid = str(resolved.avatar["StrId"])
    nodes = set((resolved.raw.get("talent") or {}).get("latestPassiveSkillNodes") or [])
    tiers = [(2, f"{sid}_passive_skill_0_2"), (1, f"{sid}_passive_skill_0_1")]
    tier = next((tier for tier, node in tiers if node in nodes), 0)
    if sid == "chr_0020_meurs" and tier:
        value = math.floor(sheet.integer(42) / 10) * (1.2 if tier == 2 else 1)
        sheet.add(3, value, "Addition", source=f"passive:{sid}:{tier}")
    elif sid == "chr_0015_lifeng" and tier:
        return (sheet.integer(41) + sheet.integer(42)) * (0.0015 if tier == 2 else 0.001)
    return 0.0


def calculate_character(tables: dict[str, Any], resolved: ResolvedCharacter) -> CalculationResult:
    """Calculate static sheet values without copying display text into arithmetic.

    Conditional combat effects are not synthesized from descriptions. The result
    retains every declared static property and its contribution provenance.
    """
    avatar = resolved.avatar
    raw = resolved.raw
    level = _level(raw.get("level", 1), source="character")
    main, secondary = int(avatar["MainAttrId"]), int(avatar["SubAttrId"])
    sheet = StatSheet(main, secondary)
    for stat_id, growth in avatar.get("BaseAttributes", {}).items():
        value = float(growth["BaseValue"]) + float(growth.get("AddValue", 0)) * (level - 1)
        if int(stat_id) == 15:
            value /= 100
        sheet.add(stat_id, value, source="character:base")
    sheet.add(1, _curve(avatar["BaseHpByLevel"], level, source="character:hp"), source="character:hp")
    sheet.add(
        2, _curve(avatar["BaseAtkByLevel"], level, source="character:attack"), source="character:attack"
    )
    sheet.add(44, 1.0, source="character:ultimate-gain")
    sheet.add(10, 0.5, source="character:critical-damage")
    for potential in avatar.get("PotAttributes", []):
        if int(raw.get("potentialLevel", 0)) >= int(potential["Level"]):
            for stat_id, prop in potential["Attrs"].items():
                sheet.add(stat_id, prop["Value"], prop["Formula"], source=f"potential:{potential['Level']}")
    weapon = resolved.weapon
    if weapon is not None:
        weapon_raw = raw.get("weapon") or {}
        curve = tables["weapon_meta"]["LevelCurves"].get(weapon["LevelTemplateId"])
        if curve is None:
            raise MappingError("weapon level curve is missing")
        sheet.add(
            2,
            _curve(curve, _level(weapon_raw.get("level", 1), source="weapon"), source="weapon"),
            source="weapon:attack",
        )
        for skill_id, skill_level in zip(weapon["SkillList"], resolved.weapon_skill_levels, strict=True):
            _skill(sheet, tables, skill_id, skill_level, f"weapon:{skill_id}")
    suits: Counter[str] = Counter()
    for equip in resolved.equipment:
        if equip.record.get("SuitId"):
            suits[equip.record["SuitId"]] += 1
        for modifier, slot in zip(equip.record["AttrModifiers"], equip.modifier_slots, strict=True):
            index = equip.enhancements.get(str(slot), 0) if slot else 0
            values = modifier["Values"]
            if index < 0 or index >= len(values):
                raise ConfigError(
                    "gear enhancement is outside the asset curve", context={"item_id": equip.item_id}
                )
            sheet.add(
                modifier["AttrType"],
                float(values[index]),
                modifier["Formula"],
                source=f"equipment:{equip.slot}:{equip.item_id}:{slot}",
            )
    for suit_id, pieces in suits.items():
        if pieces >= 3:
            suit = tables["equips"]["Suits"].get(suit_id)
            if suit is None:
                raise MappingError("equipment suit is missing", context={"suit_id": suit_id})
            _skill(sheet, tables, suit["SkillId"], 1, f"suit:{suit_id}")
    talent = raw.get("talent") or {}
    for node in dict.fromkeys(resolved.attribute_nodes or talent.get("attrNodes") or []):
        attrs = avatar.get("AttributeNodes", {}).get(node)
        if attrs is None:
            raise MappingError("unlocked attribute node is missing", context={"node_id": node})
        for stat_id, value in attrs.items():
            sheet.add(stat_id, value, source=f"talent:{node}")
    sheet.add(1, sheet.integer(39) * 5, source="derived:strength-health")
    sheet.add(30, sheet.integer(42) * 0.001, "Addition", source="derived:will-treatment")
    passive_ratio = _passives(sheet, resolved)
    attack_ratio = sheet.integer(main) * 0.005 + sheet.integer(secondary) * 0.002
    before_attack = sheet.value(2)
    sheet.add(2, before_attack * attack_ratio, "Addition", source="derived:attribute-attack")
    if passive_ratio:
        sheet.add(2, before_attack * passive_ratio, "Addition", source="passive:lifeng:attribute-attack")
    values = sheet.output()
    return CalculationResult(
        values=values,
        units={stat: stat_unit(stat) for stat in values},
        contributions=tuple(sheet.contributions),
        main_attribute=main,
        sub_attribute=secondary,
        warnings=resolved.warnings,
    )
