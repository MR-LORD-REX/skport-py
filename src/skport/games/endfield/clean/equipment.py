"""Render-ready gear while keeping unknown numeric affixes explicitly absent."""

from __future__ import annotations

from typing import Any

from skport.config import ImageSource
from skport.games.endfield.calc.types import ResolvedCharacter, ResolvedEquipment
from skport.games.endfield.clean.common import image_links, numeric, rarity
from skport.games.endfield.clean.stats import GROUP_LABELS, stat_modifier, stat_name
from skport.games.endfield.models.equipment import Equipment, EquipmentSlot, StatLine
from skport.games.endfield.resolve.gear import PROPERTY_IDS, property_group

SLOTS = {
    "bodyEquip": EquipmentSlot.BODY,
    "armEquip": EquipmentSlot.ARMS,
    "firstAccessory": EquipmentSlot.ACCESSORY1,
    "secondAccessory": EquipmentSlot.ACCESSORY2,
}


def _resolved_lines(
    piece: ResolvedEquipment,
    avatar: dict[str, Any],
    labels: dict[str, str],
) -> list[StatLine]:
    metadata = piece.raw.get("equipData") or {}
    keys = metadata.get("properties") or []
    grouped: dict[int, list[dict[str, Any]]] = {}
    for modifier, slot in zip(piece.record["AttrModifiers"], piece.modifier_slots, strict=True):
        if slot:
            grouped.setdefault(slot, []).append(modifier)
    result = []
    for slot, modifiers in sorted(grouped.items()):
        level = piece.enhancements.get(str(slot), 0)
        effects = [
            stat_modifier(mod["AttrType"], float(mod["Values"][level]), mod["Formula"], avatar)
            for mod in modifiers
        ]
        ids = [effect.id for effect in effects]
        wire_key = str(keys[slot - 1]) if slot <= len(keys) else ""
        name = labels.get(wire_key) or GROUP_LABELS.get(frozenset(ids)) or stat_name(ids[0], labels)
        first = effects[0]
        result.append(
            StatLine(
                name=name,
                value=first.value,
                unit=first.unit,
                level=level,
                max_level=min(len(mod["Values"]) - 1 for mod in modifiers),
                stat_ids=ids,
                formula=first.formula,
                effects=effects,
            )
        )
    return result


def build_equipment(
    raw_character: dict[str, Any],
    resolved: ResolvedCharacter | None,
    tables: dict[str, Any] | None,
    preferred: ImageSource,
    labels: dict[str, str] | None = None,
) -> list[Equipment]:
    """Retain slot identity, both artwork sources and observed enhancement state."""
    found = {piece.slot: piece for piece in resolved.equipment} if resolved is not None else {}
    result = []
    for field, slot in SLOTS.items():
        raw = raw_character.get(field)
        if not raw:
            continue
        metadata = raw.get("equipData") or {}
        piece = found.get(field)
        enhancements = raw.get("enhance") or {}
        suit = metadata.get("suit") or {}
        lines: list[StatLine] = []
        if piece is not None and resolved is not None:
            lines = _resolved_lines(piece, resolved.avatar, labels or {})
        else:
            for index, key in enumerate(metadata.get("properties") or [], start=1):
                if not key:
                    continue
                normalized = str(key).removeprefix("equip_attr_").removeprefix("equip_")
                ids = list(property_group(key)) if normalized in PROPERTY_IDS else []
                name = (labels or {}).get(key) or GROUP_LABELS.get(frozenset(ids))
                name = name or (stat_name(ids[0], labels) if ids else str(key))
                lines.append(
                    StatLine(
                        name=name,
                        value=None,
                        level=int(numeric(enhancements.get(str(index)))),
                        stat_ids=ids,
                    )
                )
        defense = numeric(metadata["baseAttrValue"]) if metadata.get("baseAttrValue") is not None else None
        result.append(
            Equipment(
                slot=slot,
                id=str(metadata.get("id") or raw.get("equipId") or ""),
                template_id=piece.item_id if piece is not None else None,
                name=str(metadata.get("name") or ""),
                rarity=rarity(metadata.get("rarity")),
                suit_id=piece.record.get("SuitId") if piece is not None else suit.get("id"),
                suit_name=str(suit.get("name") or ""),
                icon=image_links(
                    metadata.get("iconUrl"), piece.record.get("Icon") if piece else None, preferred
                ),
                defense=defense,
                stat_lines=lines,
                enhance_count=sum(int(numeric(value)) for value in enhancements.values()),
                max_enhance=sum(line.max_level for line in lines) if piece is not None else None,
            )
        )
    return result
