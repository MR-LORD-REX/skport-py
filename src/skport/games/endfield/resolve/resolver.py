"""Resolve SKPORT metadata to canonical Enka calculation records."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from skport.errors import MappingError
from skport.games.endfield.calc.levels import weapon_skill_levels
from skport.games.endfield.calc.types import ResolvedCharacter
from skport.games.endfield.resolve.gear import SLOTS, rarity, resolve_equipment
from skport.games.endfield.resolve.indexes import choose, name_index, name_key
from skport.games.endfield.resolve.weapon import observed_skill_level, ordered_weapon_skills

WEAPON_TYPES = {
    "weapon_type_sword": "Sword",
    "weapon_type_claym": "Claymores",
    "weapon_type_lance": "Lance",
    "weapon_type_pistol": "Pistol",
    "weapon_type_wand": "Wand",
}


def _character(tables: dict[str, Any], raw: dict[str, Any], revision: str) -> tuple[str, dict[str, Any]]:
    metadata = raw.get("charData") or {}
    talent = raw.get("talent") or {}
    passive_nodes = [str(node) for node in talent.get("latestPassiveSkillNodes") or []]
    nodes = [str(node) for value in talent.values() if isinstance(value, list) for node in value]
    nodes.extend(
        str(node.get("id", ""))
        for group in ("abilityTalents", "combatTalents", "cultivationTalents")
        for node in metadata.get(group) or []
    )

    def matching(node_ids: list[str]) -> set[str]:
        return {
            str(key)
            for key, avatar in tables["avatars"].items()
            if avatar.get("StrId")
            and any(
                node == avatar["StrId"]
                or node.startswith(avatar["StrId"] + "_")
                or node.startswith("fac_" + avatar["StrId"] + "_")
                or node.startswith("spaceship_skill_" + avatar["StrId"] + "_")
                for node in node_ids
            )
        }

    candidates = matching(passive_nodes) or matching(nodes)
    if not candidates:
        candidates = name_index(tables["avatars"], tables["locs"]).get(
            name_key(str(metadata.get("name", ""))),
            set(),
        )
    key, avatar, _ = choose(tables["avatars"], candidates, kind="character", revision=revision)
    return key, avatar


def _attribute_nodes(
    tables: dict[str, Any],
    raw: dict[str, Any],
    avatar: dict[str, Any],
) -> tuple[tuple[str, ...], int | None]:
    """Bridge display-variant nodes only when their canonical values agree."""
    canonical = avatar.get("AttributeNodes", {})
    result: list[str] = []
    display_id = None
    for node in (raw.get("talent") or {}).get("attrNodes") or []:
        if node in canonical:
            result.append(node)
            continue
        variants = [
            (key, other)
            for key, other in tables["avatars"].items()
            if node in other.get("AttributeNodes", {})
        ]
        suffix = str(node).rsplit("_", 1)[-1]
        candidates = [
            key
            for key, values in canonical.items()
            if key.endswith("_" + suffix)
            and any(other["AttributeNodes"][node] == values for _, other in variants)
        ]
        if len(candidates) != 1:
            raise MappingError("attribute node has no unique canonical equivalent", context={"node_id": node})
        result.append(candidates[0])
        if len(variants) == 1:
            display_id = int(variants[0][0])
    return tuple(result), display_id


def _weapon(
    tables: dict[str, Any], raw: dict[str, Any], revision: str
) -> tuple[str, dict[str, Any], tuple[str, ...]]:
    metadata = raw.get("weaponData") or {}
    records = tables["weapons"]
    candidates = name_index(records, tables["locs"]).get(name_key(str(metadata.get("name", ""))), set())
    weapon_type = WEAPON_TYPES.get(str((metadata.get("type") or {}).get("key", "")))
    wanted_rarity = rarity(metadata.get("rarity"))
    candidates = {
        key
        for key in candidates
        if (wanted_rarity is None or records[key]["Rarity"] == wanted_rarity)
        and (weapon_type is None or records[key]["WeaponType"] == weapon_type)
    }
    stems = {
        str(skill.get("key", "")).removeprefix("sk_")
        for skill in raw.get("skills") or []
        if str(skill.get("key", "")).startswith("sk_wpn_")
    }
    icon_matches = {key for key in candidates if PurePosixPath(records[key]["Icon"]).stem in stems}
    if icon_matches:
        candidates = icon_matches
    return choose(
        records,
        candidates,
        kind="weapon",
        revision=revision,
        equivalent_fields=(
            "Rarity",
            "WeaponType",
            "LevelTemplateId",
            "BreakthroughTemplateId",
            "TalentTemplateId",
            "SkillList",
        ),
    )


def _essence(
    tables: dict[str, Any],
    raw: dict[str, Any],
    revision: str,
) -> tuple[int | None, tuple[tuple[int, int], ...]]:
    gem = raw.get("gem") or {}
    metadata = gem.get("gemData") or {}
    if not metadata:
        return None, ()
    templates = tables["gems"].get("TemplateItems", {})
    template_stem = metadata.get("templateId")
    candidates = {
        key for key, entry in templates.items() if PurePosixPath(entry["Icon"]).stem == template_stem
    }
    template_id, _, _ = choose(templates, candidates, kind="essence template", revision=revision)
    tags = {
        (entry.get("skill") or {}).get("key"): entry.get("gemTagId")
        for entry in (raw.get("weaponData") or {}).get("skillInfos") or []
    }
    tags_by_term = {skill.get("gemTermId"): tags.get(skill.get("key")) for skill in raw.get("skills") or []}
    terms = tables["gems"]["TermNums"]
    result = []
    for index, term in enumerate(gem.get("terms") or [], start=1):
        tag = tags_by_term.get(term.get("id"))
        candidates = {
            key
            for key, canonical in terms.items()
            if canonical["TermType"] == index and canonical["TagId"] == tag
        }
        if not candidates:
            candidates = {
                key
                for key, canonical in terms.items()
                if canonical["TermType"] == index
                and any(
                    name_key(str(names.get(str(canonical.get("TagNameHash")), "")))
                    == name_key(str(term.get("name", "")))
                    for names in tables["locs"].values()
                )
            }
        term_id, _, _ = choose(terms, candidates, kind="essence term", revision=revision)
        result.append((int(term_id), int(term.get("cost", 0))))
    return int(template_id), tuple(result)


def resolve_character(
    tables: dict[str, Any],
    raw_char: dict[str, Any],
    revision: str = "",
) -> ResolvedCharacter:
    """Resolve structural inputs, refusing to interpret opaque hashes as templates."""
    avatar_id, avatar = _character(tables, raw_char, revision)
    attribute_nodes, display_avatar_id = _attribute_nodes(tables, raw_char, avatar)
    equipment = []
    warnings: list[str] = []
    for slot in SLOTS:
        if raw_char.get(slot):
            item, notices = resolve_equipment(tables, slot, raw_char[slot], revision=revision)
            equipment.append(item)
            warnings.extend(notices)
    weapon_id, weapon = None, None
    skill_levels: tuple[int, ...] = ()
    gem_template: int | None = None
    gem_terms: tuple[tuple[int, int], ...] = ()
    weapon_raw = raw_char.get("weapon")
    if weapon_raw:
        key, weapon, notices = _weapon(tables, weapon_raw, revision)
        weapon_id = int(key)
        warnings.extend(notices)
        gem_template, gem_terms = _essence(tables, weapon_raw, revision)
        provided = ordered_weapon_skills(tables, weapon_raw, weapon)
        if provided:
            skill_levels = tuple(observed_skill_level(skill.get("level", 0)) for skill in provided)
        else:
            skill_levels = weapon_skill_levels(
                tables,
                weapon,
                int(weapon_raw.get("refineLevel", 0)),
                int(weapon_raw.get("breakthroughLevel", 0)),
                gem_terms,
            )
    return ResolvedCharacter(
        avatar_id=int(avatar_id),
        avatar=avatar,
        raw=raw_char,
        weapon_id=weapon_id,
        weapon=weapon,
        equipment=tuple(equipment),
        weapon_skill_levels=skill_levels,
        gem_template_id=gem_template,
        gem_terms=gem_terms,
        revision=revision,
        warnings=tuple(warnings),
        display_avatar_id=display_avatar_id,
        attribute_nodes=attribute_nodes,
    )
