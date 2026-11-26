"""Normalize inventory with stable game IDs and explicit quantities."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ValidationError

from skport.config import ImageSource
from skport.errors import DecodeError
from skport.games.endfield.clean.common import image_links, wire_list, wire_object
from skport.games.endfield.models.base import ModelIssue
from skport.games.endfield.models.inventory import (
    Inventory,
    InventoryEntry,
    InventoryMetadataSource,
    InventoryOperator,
    InventorySkill,
)
from skport.games.endfield.models.wiki import WikiSummary

_WIKI_CATEGORIES = {"operators": "1", "weapons": "2", "equipment": "4"}
_OWNER_SLOTS = (
    ("weapons", "weapon", "weaponData", "weaponId"),
    ("equipment", "bodyEquip", "equipData", "equipId"),
    ("equipment", "armEquip", "equipData", "equipId"),
    ("equipment", "firstAccessory", "equipData", "equipId"),
    ("equipment", "secondAccessory", "equipData", "equipId"),
    ("tactical_items", "tacticalItem", "tacticalItemData", "tacticalItemId"),
)


def _identifier(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    return str(value).strip() or None


def _wiki_id(value: Any) -> str | None:
    identifier = _identifier(value)
    return identifier if identifier != "0" else None


def _entry(
    record: dict[str, Any],
    item_id: str,
    preferred: ImageSource,
    lang: str | None,
) -> InventoryEntry:
    count = record.get("ownedCount")
    source = InventoryMetadataSource(source="inventory", locale=lang)
    icon = image_links(record.get("icon") or record.get("iconUrl"), preferred=preferred)
    name = record.get("name") or ""
    wiki_id = _wiki_id(record.get("wikiItemId"))
    item = InventoryEntry(
        id=item_id,
        name=name,
        name_source=source if name else None,
        icon=icon,
        icon_source=source if icon.url else None,
        wiki_item_id=wiki_id,
        wiki_item_source=source if wiki_id else None,
        owned=record.get("owned"),
        count=count,
    )
    if item.owned is None and item.count is not None:
        item.owned = item.count > 0
    return item


def _entries(
    raw: dict[str, Any],
    group: str,
    id_field: str,
    preferred: ImageSource,
    lang: str | None,
) -> dict[str, InventoryEntry]:
    items = {}
    for key, value in wire_object(raw.get(group, {}), group).items():
        record = wire_object(value, group)
        item = _entry(record, str(record.get(id_field) or key), preferred, lang)
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


def inventory(data: Any, preferred: ImageSource, *, lang: str | None = None) -> Inventory:
    """Decode the inventory wrapper without fetching additional item metadata."""
    raw = wire_object(wire_object(data, "inventory").get("userGameData"), "userGameData")
    operators = {}
    try:
        for key, value in wire_object(raw.get("userChars", {}), "userChars").items():
            record = wire_object(value, "operator inventory entry")
            item = _entry(record, str(record.get("charId") or key), preferred, lang)
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
            weapons=_entries(raw, "userWeapons", "weaponId", preferred, lang),
            equipment=_entries(raw, "userEquips", "equipId", preferred, lang),
            tactical_items=_entries(raw, "userTacticalItems", "tacticalItemId", preferred, lang),
        )
    except (KeyError, ValidationError) as exc:
        raise DecodeError("invalid inventory fields") from exc


@dataclass(frozen=True, slots=True)
class _CardMetadata:
    wiki_item_id: str | None
    name: str | None
    icon: str | None


def _owner_items(result: Inventory, response: Any) -> dict[tuple[str, str], set[_CardMetadata]]:
    items: dict[tuple[str, str], set[_CardMetadata]] = defaultdict(set)
    if response is None:
        return items
    detail = wire_object(wire_object(response, "inventory owner card").get("detail"), "owner card detail")
    base = wire_object(detail.get("base") or {}, "owner card base")
    for expected, field in ((result.game_uid, "roleId"), (result.server_id, "serverId")):
        actual = _identifier(base.get(field))
        if expected and actual and actual != expected:
            raise DecodeError("inventory owner card has a different role or server")

    def add(
        family: str, item: dict[str, Any], metadata: dict[str, Any], id_field: str, icon_field: str
    ) -> None:
        item_id = _identifier(item.get(id_field)) or _identifier(metadata.get("id"))
        if item_id:
            items[family, item_id].add(
                _CardMetadata(
                    wiki_item_id=_wiki_id(item.get("wikiItemId")) or _wiki_id(metadata.get("wikiItemId")),
                    name=metadata.get("name") if isinstance(metadata.get("name"), str) else None,
                    icon=metadata.get(icon_field) if isinstance(metadata.get(icon_field), str) else None,
                )
            )

    for value in wire_list(detail.get("chars"), "owner card characters"):
        character = wire_object(value, "owner card character")
        add(
            "operators",
            character,
            wire_object(character.get("charData") or {}, "owner card operator"),
            "id",
            "avatarSqUrl",
        )
        for family, slot, data_field, id_field in _OWNER_SLOTS:
            equipped = wire_object(character.get(slot) or {}, f"owner card {slot}")
            if equipped:
                add(
                    family,
                    equipped,
                    wire_object(equipped.get(data_field) or {}, f"owner card {data_field}"),
                    id_field,
                    "iconUrl",
                )
    return items


def _inventory_items(result: Inventory) -> Iterator[tuple[str, InventoryEntry]]:
    for family, entries in (
        ("operators", result.operators),
        ("weapons", result.weapons),
        ("equipment", result.equipment),
        ("tactical_items", result.tactical_items),
    ):
        for entry in entries.values():
            yield family, entry


def _unique(values: Iterable[str | None]) -> tuple[str | None, bool]:
    present = {value for value in values if value}
    return (present.pop(), False) if len(present) == 1 else (None, bool(present))


def inventory_wiki_ids(result: Inventory, owner_card: Any = None) -> set[str]:
    """Collect unambiguous article IDs explicitly supplied for these inventory entries."""
    try:
        card = _owner_items(result, owner_card)
    except DecodeError:
        card = {}
    ids: set[str] = set()
    for family, entry in _inventory_items(result):
        card_id, _ = _unique(item.wiki_item_id for item in card.get((family, entry.id), ()))
        wiki_id = entry.wiki_item_id or card_id
        if wiki_id:
            ids.add(wiki_id)
    return ids


def enrich_inventory(
    result: Inventory,
    preferred: ImageSource,
    *,
    lang: str,
    owner_card: Any = None,
    catalog: Iterable[WikiSummary] = (),
    summaries: Mapping[str, WikiSummary] | None = None,
) -> Inventory:
    """Fill missing display fields from verified wiki or same-role card identities."""
    result = result.model_copy(deep=True)
    try:
        card = _owner_items(result, owner_card)
    except DecodeError as exc:
        card = {}
        result.issues.append(
            ModelIssue(code="inventory_card_invalid", message=exc.message, path="owner_card")
        )

    owner_source = InventoryMetadataSource(source="owner_card", locale=lang)
    catalog_by_id: dict[str, WikiSummary] = {}
    associations: dict[tuple[str, str], dict[str, WikiSummary]] = defaultdict(dict)
    for summary in catalog:
        catalog_by_id[summary.id] = summary
        if summary.related_game_id:
            associations[summary.category.key, summary.related_game_id][summary.id] = summary

    for family, entry in _inventory_items(result):
        path = f"{family}.{entry.id}"
        records = card.get((family, entry.id), ())
        card_id, conflict_id = _unique(item.wiki_item_id for item in records)
        card_name, conflict_name = _unique(item.name for item in records)
        card_icon, conflict_icon = _unique(item.icon for item in records)
        if (
            conflict_id
            or conflict_name
            or conflict_icon
            or (entry.wiki_item_id and card_id and entry.wiki_item_id != card_id)
        ):
            result.issues.append(
                ModelIssue(
                    code="inventory_card_ambiguous",
                    message="Inventory or owner card display records disagree",
                    path=path,
                )
            )
        if not entry.wiki_item_id and card_id:
            entry.wiki_item_id = card_id
            entry.wiki_item_source = owner_source

        item, source = _matched_wiki_item(
            result, entry, family, catalog_by_id, associations, summaries or {}, path
        )
        if item and source:
            if not entry.wiki_item_id:
                entry.wiki_item_id = item.id
                entry.wiki_item_source = source
            if not entry.name and item.name:
                entry.name = item.name
                entry.name_source = source
            if not entry.icon.url and item.icon.url:
                entry.icon = item.icon.model_copy(update={"preferred": preferred})
                entry.icon_source = source
        if not entry.name and card_name:
            entry.name = card_name
            entry.name_source = owner_source
        if not entry.icon.url and card_icon:
            try:
                entry.icon = image_links(card_icon, preferred=preferred)
            except ValidationError:
                result.issues.append(
                    ModelIssue(
                        code="inventory_card_icon_invalid",
                        message="Owner card icon is not a valid artwork URL",
                        path=path,
                    )
                )
            else:
                entry.icon_source = owner_source
    return result


def _matched_wiki_item(
    result: Inventory,
    entry: InventoryEntry,
    family: str,
    catalog: Mapping[str, WikiSummary],
    associations: Mapping[tuple[str, str], Mapping[str, WikiSummary]],
    summaries: Mapping[str, WikiSummary],
    path: str,
) -> tuple[WikiSummary | None, InventoryMetadataSource | None]:
    category = _WIKI_CATEGORIES.get(family, "")
    source: Literal["wiki_catalog", "wiki_batch"]
    if entry.wiki_item_id:
        item = catalog.get(entry.wiki_item_id)
        source = "wiki_catalog" if item else "wiki_batch"
        item = item or summaries.get(entry.wiki_item_id)
        if item and (
            item.id != entry.wiki_item_id
            or (category and item.category.key and item.category.key != category)
            or (item.related_game_id and item.related_game_id != entry.id)
        ):
            result.issues.append(
                ModelIssue(
                    code="inventory_wiki_conflict",
                    message="The explicit wiki article has a different identity",
                    path=path,
                )
            )
            return None, None
    else:
        candidates = associations.get((category, entry.id), {}) if category else {}
        if len(candidates) > 1:
            result.issues.append(
                ModelIssue(
                    code="inventory_wiki_ambiguous",
                    message="More than one wiki article matches this game ID",
                    path=path,
                )
            )
        item = next(iter(candidates.values())) if len(candidates) == 1 else None
        source = "wiki_catalog"
    return (item, InventoryMetadataSource(source=source, locale=item.locale)) if item else (None, None)
