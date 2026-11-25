"""Observed skill levels and display-ready canonical effects."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from skport.games.endfield.models.base import OutputModel
from skport.games.endfield.models.images import ImageLinks, SemanticLabel
from skport.games.endfield.models.stats import StatModifier


class SkillForm(OutputModel):
    """One named skill form with its original description parameters."""

    name: str = ""
    description: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class Skill(OutputModel):
    """Expose stable identity, localized description and observed effective level."""

    id: str = ""
    key: str = ""
    name: str = ""
    type: SemanticLabel | None = None
    icon: ImageLinks = Field(default_factory=ImageLinks)
    level: int = Field(default=0, ge=0)
    max_level: int = Field(default=12, ge=0)
    # Weapon display provenance: unlock/refinement base plus applied essence bonus.
    # Ordinary skills and incomplete assets leave the optional split unknown.
    tag_id: int | str | None = None
    base_level: int | None = Field(default=None, ge=0)
    bonus_level: int | None = Field(default=None, ge=0)
    description: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    effects: list[StatModifier] = Field(default_factory=list)
    forms: list[SkillForm] = Field(default_factory=list)
    raw_description: str = ""
    level_params: dict[str, Any] = Field(default_factory=dict)
