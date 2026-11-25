"""Observed weapon progression and resolved essence/skill metadata."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from skport.config import ImageSource
from skport.errors import MappingError
from skport.games.endfield.calc.levels import weapon_skill_levels
from skport.games.endfield.calc.types import ResolvedCharacter
from skport.games.endfield.clean.common import description, image_links, numeric, rarity
from skport.games.endfield.clean.stats import stat_modifier
from skport.games.endfield.models.skills import Skill
from skport.games.endfield.models.weapon import Gem, GemTerm, Weapon
from skport.games.endfield.resolve.weapon import ordered_weapon_skills


def _item_icon(path: str | None) -> str | None:
    """Place canonical weapon/essence files in the observed CDN item folder."""
    return f"/ui/ef/itemicon/{PurePosixPath(path).name}" if path else None


def _gem(
    raw: dict[str, Any],
    resolved: ResolvedCharacter | None,
    tables: dict[str, Any] | None,
    preferred: ImageSource,
) -> Gem | None:
    data = raw.get("gem") or {}
    metadata = data.get("gemData") or {}
    if not metadata:
        return None
    canonical = tables["gems"] if tables is not None and resolved is not None else {}
    base = canonical.get("TemplateItems", {}).get(str(resolved.gem_template_id), {}) if resolved else {}
    terms = []
    badge_icon = None
    for index, item in enumerate(data.get("terms") or []):
        term_id = (
            resolved.gem_terms[index][0] if resolved is not None and index < len(resolved.gem_terms) else None
        )
        term = canonical.get("TermNums", {}).get(str(term_id), {})
        if term.get("TermType") == 3:
            badge_icon = term.get("TagIcon")
        terms.append(
            GemTerm(
                id=str(item.get("id") or ""),
                name=str(item.get("name") or ""),
                tag_id=term.get("TagId"),
                points=int(numeric(item.get("cost"))),
                icon=image_links(item.get("iconUrl") or item.get("icon"), term.get("TagIcon"), preferred),
            )
        )
    base_links = image_links(enka=_item_icon(base.get("Icon")), preferred=preferred)
    icon = image_links(metadata.get("icon") or data.get("icon"), badge_icon, preferred)
    return Gem(
        id=str(data.get("id") or ""),
        template_id=resolved.gem_template_id
        if resolved and resolved.gem_template_id is not None
        else metadata.get("templateId"),
        name=str(metadata.get("name") or ""),
        rarity=rarity(metadata.get("templateId")) or None,
        icon=icon,
        base_icon=base_links,
        terms=terms,
    )


def build_weapon(
    raw_character: dict[str, Any],
    resolved: ResolvedCharacter | None,
    tables: dict[str, Any] | None,
    preferred: ImageSource,
) -> Weapon | None:
    """Keep all observed levels and derive effects only from identified assets."""
    raw = raw_character.get("weapon")
    if not raw:
        return None
    metadata = raw.get("weaponData") or {}
    canonical = resolved.weapon if resolved is not None else None
    skills = []
    effects = []
    infos = {(entry.get("skill") or {}).get("key"): entry for entry in metadata.get("skillInfos") or []}
    entries = (
        ordered_weapon_skills(tables, raw, canonical) if tables and canonical else raw.get("skills") or []
    )
    gem = _gem(raw, resolved, tables, preferred)
    bonus_points: dict[str, int] = {}
    if gem is not None:
        for term in gem.terms:
            if term.tag_id is not None and str(term.tag_id):
                tag = str(term.tag_id)
                bonus_points[tag] = bonus_points.get(tag, 0) + term.points
    base_levels = None
    if canonical is not None and tables is not None:
        try:
            # Refine/breakthrough unlocks are base levels; essence points are extra.
            base_levels = weapon_skill_levels(
                tables,
                canonical,
                int(numeric(raw.get("refineLevel"))),
                int(numeric(raw.get("breakthroughLevel"))),
            )
        except (MappingError, KeyError):
            # Partial assets must retain the observed total without inventing a split.
            pass
    if not entries and canonical and tables is not None and resolved is not None:
        derived = []
        passive_key = "sk_" + PurePosixPath(canonical["Icon"]).stem
        for skill_id, level in zip(canonical["SkillList"], resolved.weapon_skill_levels, strict=True):
            tag = tables["skills"][str(skill_id)].get("TagId")
            candidates = [
                entry
                for entry in metadata.get("skills") or []
                if (
                    infos.get(entry.get("key"), {}).get("gemTagId") == tag
                    if tag
                    else entry.get("key") == passive_key
                )
            ]
            definition = candidates[0] if len(candidates) == 1 else {}
            derived.append(
                {
                    "key": definition.get("key", ""),
                    "name": definition.get("value", ""),
                    "level": level,
                }
            )
        entries = tuple(derived)
    for index, entry in enumerate(entries):
        level = int(numeric(entry.get("level")))
        skill_id = (
            canonical["SkillList"][index] if canonical and index < len(canonical["SkillList"]) else None
        )
        skill = tables["skills"].get(str(skill_id), {}) if tables is not None else {}
        modifiers = []
        if level > 0:
            for key, prop in skill.get("PropMap", {}).items():
                values = prop["Values"]
                if not values or (len(values) > 1 and level > len(values)):
                    continue
                modifiers.append(
                    stat_modifier(
                        key,
                        float(values[min(level, len(values)) - 1]),
                        prop["Formula"],
                        resolved.avatar if resolved is not None else None,
                    )
                )
        effects.extend(modifiers)
        info = infos.get(entry.get("key"), {})
        tag_id = skill.get("TagId")
        if tag_id is None or tag_id == "":
            tag_id = info.get("gemTagId")
        base_level, bonus_level = None, None
        if base_levels is not None and index < len(base_levels):
            base = base_levels[index]
            bonus = level - base
            if 0 <= bonus <= bonus_points.get(str(tag_id), 0):
                base_level, bonus_level = base, bonus
        term = (
            tables["gems"]["TermNums"].get(str(resolved.gem_terms[index][0]), {})
            if tables is not None and resolved is not None and index < len(resolved.gem_terms)
            else {}
        )
        skills.append(
            Skill(
                id=str(skill_id) if skill_id is not None else str(entry.get("key") or ""),
                key=str(entry.get("key") or ""),
                name=str(entry.get("name") or ""),
                level=level,
                max_level=int(numeric(entry.get("currentMaxLevel"), numeric(info.get("maxLevel"), 9))),
                tag_id=tag_id,
                base_level=base_level,
                bonus_level=bonus_level,
                description=description(str(entry.get("desc") or ""), entry.get("descParams")),
                params=entry.get("descParams") or {},
                effects=modifiers,
                icon=image_links(entry.get("iconUrl"), term.get("TagIcon"), preferred),
            )
        )
    base_attack = None
    if canonical and tables is not None:
        curve = tables["weapon_meta"]["LevelCurves"].get(canonical["LevelTemplateId"])
        level = int(numeric(raw.get("level"), 1))
        if curve is not None and 1 <= level <= len(curve):
            base_attack = float(curve[level - 1])
    return Weapon(
        id=str(metadata.get("id") or ""),
        template_id=resolved.weapon_id if resolved else None,
        str_id=PurePosixPath(canonical["Icon"]).stem if canonical else None,
        name=str(metadata.get("name") or ""),
        level=int(numeric(raw.get("level"), 1)),
        refinement=int(numeric(raw.get("refineLevel"))),
        breakthrough=int(numeric(raw.get("breakthroughLevel"))),
        rarity=rarity(metadata.get("rarity")),
        base_attack=base_attack,
        images=image_links(
            metadata.get("iconUrl"), _item_icon(canonical.get("Icon")) if canonical else None, preferred
        ),
        skills=skills,
        effects=effects,
        gem=gem,
    )
