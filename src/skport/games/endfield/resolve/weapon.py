"""Match observed weapon skills by stable identities rather than array order."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from skport.errors import ConfigError, MappingError


def observed_skill_level(value: Any) -> int:
    """Validate an observed effective level without truncating fractional input."""
    try:
        level = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ConfigError("weapon skill level must be a nonnegative integer") from exc
    if isinstance(value, bool) or level < 0 or (isinstance(value, float) and value != level):
        raise ConfigError("weapon skill level must be a nonnegative integer")
    return level


def ordered_weapon_skills(
    tables: dict[str, Any],
    raw: dict[str, Any],
    weapon: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Return wire skill entries in the canonical order used by calculation."""
    provided = raw.get("skills") or []
    if not provided:
        return ()
    if len(provided) != len(weapon["SkillList"]):
        raise MappingError("wire weapon skills do not match the canonical skill count")
    tags = {
        str((entry.get("skill") or {}).get("key") or ""): entry.get("gemTagId")
        for entry in (raw.get("weaponData") or {}).get("skillInfos") or []
    }
    passive_key = "sk_" + PurePosixPath(weapon["Icon"]).stem
    result = []
    used: set[int] = set()
    for skill_id in weapon["SkillList"]:
        canonical = tables["skills"].get(str(skill_id))
        if canonical is None:
            raise MappingError("canonical weapon skill is missing", context={"skill_id": skill_id})
        tag = canonical.get("TagId")
        candidates = [
            index
            for index, entry in enumerate(provided)
            if index not in used
            and entry.get("key")
            and (tags.get(str(entry["key"])) == tag if tag else entry["key"] == passive_key)
        ]
        if len(candidates) != 1:
            raise MappingError(
                "weapon skill has no unique canonical match",
                context={"skill_id": skill_id, "tag_id": tag},
            )
        index = candidates[0]
        used.add(index)
        result.append(provided[index])
    return tuple(result)
