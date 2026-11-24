"""Weapon progression, essence terms and stat-bearing skill effects."""

from __future__ import annotations

from pydantic import Field

from skport.games.endfield.models.base import OutputModel
from skport.games.endfield.models.images import ImageLinks
from skport.games.endfield.models.skills import Skill
from skport.games.endfield.models.stats import StatModifier


class GemTerm(OutputModel):
    """One essence socket's stable tag and observed skill points."""

    id: str = ""
    name: str = ""
    tag_id: int | str | None = None
    points: int = Field(default=0, ge=0)
    icon: ImageLinks = Field(default_factory=ImageLinks)


class Gem(OutputModel):
    """An equipped essence and its independent socket terms."""

    id: str = ""
    template_id: int | str | None = None
    name: str = ""
    rarity: int | None = Field(default=None, ge=0)
    icon: ImageLinks = Field(default_factory=ImageLinks)
    base_icon: ImageLinks = Field(default_factory=ImageLinks)
    terms: list[GemTerm] = Field(default_factory=list)


class Weapon(OutputModel):
    """Retain observed weapon state alongside optional resolved base attack."""

    id: str = ""
    template_id: int | None = Field(default=None, gt=0)
    str_id: str | None = None
    name: str = ""
    level: int = Field(default=1, ge=1)
    refinement: int = Field(default=0, ge=0)
    breakthrough: int = Field(default=0, ge=0)
    rarity: int = Field(default=0, ge=0)
    base_attack: float | None = None
    images: ImageLinks = Field(default_factory=ImageLinks)
    skills: list[Skill] = Field(default_factory=list)
    effects: list[StatModifier] = Field(default_factory=list)
    gem: Gem | None = None
