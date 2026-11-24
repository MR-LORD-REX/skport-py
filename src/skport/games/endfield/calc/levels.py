"""Weapon skill levels from refinement, breakthrough and essence points."""

from __future__ import annotations

from typing import Any

from skport.errors import ConfigError, MappingError


def weapon_skill_levels(
    tables: dict[str, Any],
    weapon: dict[str, Any],
    refine: int,
    breakthrough: int,
    gem_terms: tuple[tuple[int, int], ...] = (),
) -> tuple[int, ...]:
    """Derive bounded effective levels without turning essence points into stats."""
    meta = tables["weapon_meta"]
    refine_bounds = meta["TalentSkillLevelBounds"].get(weapon["TalentTemplateId"], {}).get(str(refine))
    break_bounds = (
        meta["BreakSkillLevelBounds"].get(weapon["BreakthroughTemplateId"], {}).get(str(breakthrough))
    )
    if break_bounds is None:
        raise MappingError("weapon breakthrough bounds are missing", context={"breakthrough": breakthrough})
    if refine_bounds is None:
        if refine != 0:
            raise MappingError("weapon refinement bounds are missing", context={"refine": refine})
        refine_bounds = [{"lowerBound": 0, "upperBound": 0} for _ in weapon["SkillList"]]
    points: dict[str, int] = {}
    for term_id, cost in gem_terms:
        term = tables["gems"]["TermNums"].get(str(term_id))
        if term is None:
            raise MappingError("essence term is missing", context={"term_id": term_id})
        if cost < 0:
            raise ConfigError("essence points cannot be negative")
        points[term["TagId"]] = points.get(term["TagId"], 0) + cost
    result = []
    for index, skill_id in enumerate(weapon["SkillList"]):
        if index >= len(refine_bounds) or index >= len(break_bounds):
            raise MappingError("weapon bounds do not cover every skill")
        lower = int(refine_bounds[index]["lowerBound"]) + int(break_bounds[index]["lowerBound"])
        upper = int(refine_bounds[index]["upperBound"]) + int(break_bounds[index]["upperBound"])
        skill = tables["skills"].get(str(skill_id))
        if skill is None:
            raise MappingError("weapon skill is missing", context={"skill_id": skill_id})
        result.append(min(lower + points.get(skill["TagId"], 0), upper))
    return tuple(result)
