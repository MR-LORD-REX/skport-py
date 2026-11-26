"""Normalize inventory with stable game IDs and explicit quantities."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from skport.config import ImageSource
from skport.errors import DecodeError
from skport.games.endfield.clean.common import image_links, wire_object
from skport.games.endfield.models.inventory import (
    Inventory,
    InventoryEntry,
    InventoryOperator,
    InventorySkill,
)


def _entry(record: dict[str, Any], item_id: str, preferred: ImageSource) -> InventoryEntry:
    count = record.get("ownedCount")
    item = InventoryEntry(
        id=item_id,
        name=record.get("name") or "",
        icon=image_links(record.get("icon") or record.get("iconUrl"), preferred=preferred),
        owned=record.get("owned"),
        count=count,
    )
    if item.owned is None and item.count is not None:
        item.owned = item.count > 0
    return item


def _entries(
    raw: dict[str, Any], group: str, id_field: str, preferred: ImageSource
) -> dict[str, InventoryEntry]:
    items = {}
    for key, value in wire_object(raw.get(group, {}), group).items():
        record = wire_object(value, group)
        item = _entry(record, str(record.get(id_field) or key), preferred)
        items[item.id] = item
    return items


def _skills(data: Any) -> dict[str, InventorySkill]:
    skills = {}
    for key, value in wire_object(data or {}, "inventory skills").items():
        skill = wire_object(value, "inventory skill")
        skills[key] = InventorySkill(
            id=str(skill.get("skillId") or key),
            level=skill["level"],
            form=skill.get("skillFormType") or "",
        )
    return skills


def inventory(data: Any, preferred: ImageSource) -> Inventory:
    """Decode the inventory wrapper without fetching additional item metadata."""
    raw = wire_object(wire_object(data, "inventory").get("userGameData"), "userGameData")
    operators = {}
    try:
        for key, value in wire_object(raw.get("userChars", {}), "userChars").items():
            record = wire_object(value, "operator inventory entry")
            item = _entry(record, str(record.get("charId") or key), preferred)
            operators[item.id] = InventoryOperator(
                **item.model_dump(),
                level=record.get("level"),
                evolution=record.get("evolvePhase"),
                potential=record.get("potentialLevel"),
                gender=record.get("gender") or "",
                skills=_skills(record.get("userSkills")),
            )
        return Inventory(
            game_uid=str(raw.get("roleId") or ""),
            server_id=str(raw.get("serverId") or ""),
            game_level=raw.get("gameLevel"),
            gender=raw.get("gender") or "",
            operators=operators,
            weapons=_entries(raw, "userWeapons", "weaponId", preferred),
            equipment=_entries(raw, "userEquips", "equipId", preferred),
            tactical_items=_entries(raw, "userTacticalItems", "tacticalItemId", preferred),
        )
    except (KeyError, ValidationError) as exc:
        raise DecodeError("invalid inventory fields") from exc
