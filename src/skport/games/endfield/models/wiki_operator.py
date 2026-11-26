"""Published operator stats and skill metrics for reference cards."""

from __future__ import annotations

from pydantic import Field

from skport.games.endfield.models.base import ModelIssue, OutputModel
from skport.games.endfield.models.images import ImageLinks
from skport.games.endfield.models.wiki import (
    WikiBlock,
    WikiCellSource,
    WikiEntry,
    WikiField,
    WikiSummary,
    WikiTag,
)


class WikiPublishedValue(OutputModel):
    """Display text and an optional unambiguous numeric reading of a cell."""

    label: str
    text: str
    source: WikiCellSource
    key: str | None = None
    value: int | float | None = None
    unit: str | None = None


class WikiStatSnapshot(OutputModel):
    """Base attributes as published for a level in the wiki."""

    level: int = Field(ge=1)
    values: list[WikiPublishedValue] = Field(default_factory=list)
    alternatives: dict[str, list[WikiPublishedValue]] = Field(default_factory=dict)


class WikiSkillRank(OutputModel):
    """One rank or mastery column of a skill's published metrics."""

    label: str
    rank: int = Field(ge=1)
    mastery: bool = False
    values: list[WikiPublishedValue] = Field(default_factory=list)


class WikiSkillReference(OutputModel):
    """An ordered skill or form with its own article tab and metrics."""

    id: str
    section_id: str
    name: str
    kind: str = ""
    description: str = ""
    icon: ImageLinks = Field(default_factory=ImageLinks)
    intro_blocks: list[WikiBlock] = Field(default_factory=list)
    ranks: list[WikiSkillRank] = Field(default_factory=list)


class WikiOperatorReference(OutputModel):
    """Static character information from a single version of the wiki article."""

    summary: WikiSummary
    requested_locale: str | None = None
    illustration: ImageLinks = Field(default_factory=ImageLinks)
    rarity: int | None = Field(default=None, ge=1)
    element: WikiTag | None = None
    profession: WikiTag | None = None
    weapon_type: WikiTag | None = None
    faction: WikiTag | None = None
    quote: str = ""
    bio: str = ""
    info_fields: list[WikiField] = Field(default_factory=list)
    stats: list[WikiStatSnapshot] = Field(default_factory=list)
    skills: list[WikiSkillReference] = Field(default_factory=list)
    lore: list[WikiEntry] = Field(default_factory=list)
    issues: list[ModelIssue] = Field(default_factory=list)
