"""Talent unlocks and all canonical attribute effects, separate from text."""

from __future__ import annotations

from typing import Any

from skport.config import ImageSource
from skport.games.endfield.calc.types import ResolvedCharacter
from skport.games.endfield.clean.common import description, image_links, numeric
from skport.games.endfield.clean.stats import stat_modifier
from skport.games.endfield.models.talents import Potential, TalentNode, TalentTree


def _unlocked(node_id: str, unlocked: set[str], *, attribute: bool = False) -> bool:
    """Infer earlier tiers only within the same named talent progression."""
    if node_id in unlocked:
        return True
    if attribute:
        return False
    prefix, _, suffix = node_id.rpartition("_")
    if not suffix.isdecimal():
        return False
    return any(
        other.rpartition("_")[0] == prefix
        and other.rpartition("_")[2].isdecimal()
        and int(other.rpartition("_")[2]) >= int(suffix)
        for other in unlocked
    )


def _talent_icon(path: str | None) -> str | None:
    """Normalize canonical talent files served from the skill-icon folder."""
    if path and path.startswith("/ui/ef/icon_talent_"):
        return path.replace("/ui/ef/", "/ui/ef/skillicon/", 1)
    return path


def build_talents(
    raw_character: dict[str, Any],
    resolved: ResolvedCharacter | None,
    tables: dict[str, Any] | None,
    preferred: ImageSource,
) -> TalentTree:
    """Keep each node and every stat on multi-property attribute unlocks."""
    metadata = raw_character.get("charData") or {}
    state = raw_character.get("talent") or {}
    unlocked = {
        str(node)
        for key, values in state.items()
        if isinstance(values, list) and (key == "attrNodes" or key.startswith("latest"))
        for node in values
    }
    canonical = resolved.avatar if resolved is not None else {}
    node_map = canonical.get("NodeSkillMap", {})
    attributes = canonical.get("AttributeNodes", {})
    raw_attributes = state.get("attrNodes") or []
    canonical_attributes = (
        dict(zip(raw_attributes, resolved.attribute_nodes, strict=True))
        if resolved and resolved.attribute_nodes
        else {}
    )
    nodes = []
    for field, kind in (
        ("abilityTalents", "attribute"),
        ("combatTalents", "combat"),
        ("cultivationTalents", "base"),
    ):
        for node in metadata.get(field) or []:
            node_id = str(node.get("id") or "")
            canonical_id = canonical_attributes.get(node_id, node_id)
            attr = attributes.get(canonical_id, {}) if kind == "attribute" else {}
            effects = [
                stat_modifier(key, float(value), "BaseAddition", canonical) for key, value in attr.items()
            ]
            entry = node_map.get(canonical_id, {})
            active = _unlocked(node_id, unlocked, attribute=kind == "attribute")
            tier = int(numeric(entry.get("Level"), 1))
            nodes.append(
                TalentNode(
                    id=node_id,
                    name=str(node.get("name") or ""),
                    kind=kind,
                    icon=image_links(node.get("iconUrl"), _talent_icon(entry.get("Icon")), preferred),
                    locked_icon=image_links(node.get("lockedIconUrl"), preferred=preferred),
                    level=tier if active else 0,
                    max_level=tier,
                    unlocked=active,
                    description=description(str(node.get("desc") or ""), node.get("descParams")),
                    effects=effects,
                )
            )
    potential_level = int(numeric(raw_character.get("potentialLevel")))
    potential_values = {int(entry["Level"]): entry for entry in canonical.get("PotAttributes", [])}
    potentials = []
    for level in range(1, max(5, potential_level, max(potential_values, default=0)) + 1):
        entry = potential_values.get(level, {})
        effects = [
            stat_modifier(key, numeric(value["Value"]), str(value["Formula"]), canonical)
            for key, value in entry.get("Attrs", {}).items()
        ]
        potentials.append(
            Potential(
                level=level,
                name=f"Potential {level}",
                unlocked=level <= potential_level,
                effects=effects,
            )
        )
    return TalentTree(nodes=nodes, potentials=potentials, unlocked_node_ids=sorted(unlocked))
