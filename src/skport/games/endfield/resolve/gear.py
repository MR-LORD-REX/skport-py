"""Identify gear from ordered stat groups rather than opaque SKPORT hashes."""

from __future__ import annotations

import math
import re
from typing import Any

from skport.errors import MappingError
from skport.games.endfield.calc.types import ResolvedEquipment
from skport.games.endfield.resolve.indexes import choose, name_index, name_key

PROPERTY_IDS = {
    "str": (39,),
    "agi": (40,),
    "wisd": (41,),
    "will": (42,),
    "max_hp": (1,),
    "atk": (2,),
    "critical_rate": (9,),
    "normal_attack_damage_increase": (17,),
    "ultimate_skill_damage_increase": (28,),
    "heal_output_increase": (29,),
    "normal_skill_damage_increase": (32,),
    "combo_skill_damage_increase": (33,),
    "ultimate_sp_gain_scalar": (44,),
    "physical_damage_increase": (50,),
    "damage_to_broken_unit_increase": (61,),
    "physical_and_spellInfliction_enhance": (87,),
    "cryst_and_pulse_damage_increase": (52, 53),
    "fire_and_natural_damage_increase": (51, 54),
    "spell_damage_increase": (51, 52, 53, 54),
    "all_skill_damage_increase": (28, 32, 33),
    "all_damage_taken_scalar": (4, 5, 6, 7, 48, 60),
    "main": (10000,),
    "sub": (10001,),
}
SLOTS = {
    "bodyEquip": "body",
    "armEquip": "hand",
    "firstAccessory": "edc",
    "secondAccessory": "edc",
}


def property_group(key: str) -> tuple[int, ...]:
    """Expand stable wire property keys, including combined elemental lines."""
    normalized = key.removeprefix("equip_attr_").removeprefix("equip_")
    if normalized not in PROPERTY_IDS:
        raise MappingError("unknown gear property key", context={"property_key": key})
    return PROPERTY_IDS[normalized]


def rarity(value: Any) -> int | None:
    """Read a stable rarity tag rather than translated display labels."""
    key = value.get("key", "") if isinstance(value, dict) else str(value or "")
    match = re.search(r"(\d+)$", key)
    return int(match[1]) if match else None


def _slots(modifiers: list[dict[str, Any]], properties: list[str]) -> tuple[int, ...] | None:
    position = 1
    result = [0]
    for slot, key in enumerate(properties, start=1):
        if not key:
            continue
        expected = property_group(key)
        segment = modifiers[position : position + len(expected)]
        if {int(mod["AttrType"]) for mod in segment} != set(expected):
            return None
        result.extend([slot] * len(expected))
        position += len(expected)
    return tuple(result) if position == len(modifiers) else None


def resolve_equipment(
    tables: dict[str, Any],
    slot: str,
    raw: dict[str, Any],
    *,
    revision: str,
) -> tuple[ResolvedEquipment, tuple[str, ...]]:
    """Resolve exact structural candidates and retain per-line enhancement slots."""
    metadata = raw.get("equipData") or {}
    items = tables["equips"]["Items"]
    suits = tables["equips"]["Suits"]
    suit_info = metadata.get("suit") or {}
    if suit_info:
        ids = name_index(suits, tables["locs"]).get(name_key(str(suit_info.get("name", ""))), set())
        _, _, warning = choose(suits, ids, kind="equipment suit", revision=revision)
        suit_ids = ids
    else:
        suit_ids, warning = {""}, ()
    desired_slot = SLOTS[slot]
    desired_rarity = rarity(metadata.get("rarity"))
    defense = float(metadata.get("baseAttrValue", 0))
    properties = list(metadata.get("properties") or [])
    candidates: set[str] = set()
    line_slots: dict[str, tuple[int, ...]] = {}
    for item_id, item in items.items():
        if item.get("SuitId", "") not in suit_ids or item.get("Rarity") != desired_rarity:
            continue
        if f"_{desired_slot}_" not in item.get("Icon", ""):
            continue
        modifiers = item.get("AttrModifiers") or []
        if not modifiers or int(modifiers[0]["AttrType"]) != 3:
            continue
        asset_defense = float(modifiers[0]["Values"][0])
        exact = math.isclose(asset_defense, defense, abs_tol=1e-6)
        truncated = defense.is_integer() and math.floor(asset_defense) == int(defense)
        if not exact and not truncated:
            continue
        grouped = _slots(modifiers, properties)
        if grouped is None:
            continue
        candidates.add(str(item_id))
        line_slots[str(item_id)] = grouped
    item_id, item, aliases = choose(
        items,
        candidates,
        kind="equipment",
        revision=revision,
        equivalent_fields=("Rarity", "SuitId", "AttrModifiers"),
    )
    enhancements = {str(key): int(value or 0) for key, value in (raw.get("enhance") or {}).items()}
    return ResolvedEquipment(
        slot, int(item_id), item, enhancements, line_slots[item_id], raw
    ), warning + aliases


def canonical_modifier_slots(item: dict[str, Any]) -> tuple[int, ...]:
    """Group known combined affixes when an input already contains canonical gear."""
    modifiers = item.get("AttrModifiers") or []
    slots: list[int] = []
    current = 0
    previous: dict[str, Any] | None = None
    for index, mod in enumerate(modifiers):
        if index == 0:
            slots.append(0)
            previous = mod
            continue
        same_curve = previous is not None and (
            previous["Formula"] == mod["Formula"] and previous["Values"] == mod["Values"]
        )
        combined = (
            previous is not None
            and same_curve
            and any(
                int(previous["AttrType"]) in group and int(mod["AttrType"]) in group
                for group in PROPERTY_IDS.values()
                if len(group) > 1
            )
        )
        if not combined:
            current += 1
        slots.append(current)
        previous = mod
    return tuple(slots)
