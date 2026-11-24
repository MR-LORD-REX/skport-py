"""Normalize set names, piece counts, descriptions and static effect metadata."""

from __future__ import annotations

from typing import Any

from skport.config import ImageSource
from skport.games.endfield.calc.types import ResolvedCharacter
from skport.games.endfield.clean.common import description, image_links
from skport.games.endfield.clean.equipment import SLOTS
from skport.games.endfield.clean.stats import stat_modifier
from skport.games.endfield.models.equipment_set import EquipmentSet


def build_equipment_sets(
    raw: dict[str, Any],
    resolved: ResolvedCharacter | None,
    tables: dict[str, Any] | None,
    preferred: ImageSource,
    locale: str,
) -> list[EquipmentSet]:
    """Preserve wire set information even when canonical data is unavailable."""
    found = {piece.slot: piece for piece in resolved.equipment} if resolved else {}
    grouped: dict[str, EquipmentSet] = {}
    for slot in SLOTS:
        metadata = ((raw.get(slot) or {}).get("equipData") or {}).get("suit") or {}
        piece = found.get(slot)
        template_id = piece.record.get("SuitId") if piece else None
        key = template_id or metadata.get("id")
        if not key:
            continue
        if key not in grouped:
            canonical = tables["equips"]["Suits"].get(template_id, {}) if tables else {}
            skill = tables["skills"].get(str(canonical.get("SkillId")), {}) if tables else {}
            locs = tables["locs"] if tables else {}
            names = locs.get(locale, locs.get("en", {}))
            name = metadata.get("name") or names.get(str(canonical.get("NameHash"))) or ""
            grouped[key] = EquipmentSet(
                id=str(metadata.get("id") or ""),
                template_id=template_id,
                name=str(name),
                icon=image_links(metadata.get("iconUrl"), canonical.get("Icon"), preferred),
                description=description(metadata.get("skillDesc") or "", metadata.get("skillDescParams")),
                effects=[
                    stat_modifier(stat_id, float(prop["Values"][0]), prop["Formula"], resolved.avatar)
                    for stat_id, prop in skill.get("PropMap", {}).items()
                    if resolved and prop.get("Values")
                ],
            )
        grouped[key].pieces += 1
    return list(grouped.values())
