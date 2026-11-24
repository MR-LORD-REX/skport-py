"""Wiki information reusable by guide and operator-reference card layouts."""

from __future__ import annotations

from pydantic import Field

from skport.games.endfield.models.base import OutputModel
from skport.games.endfield.models.images import ImageLinks, SemanticLabel
from skport.games.endfield.models.item import ItemSummary
from skport.games.endfield.models.skills import Skill
from skport.games.endfield.models.talents import TalentTree


class WikiSummary(OutputModel):
    """One catalog record with its identity, classification and artwork."""

    id: str
    name: str = ""
    category: SemanticLabel = Field(default_factory=SemanticLabel)
    icon: ImageLinks = Field(default_factory=ImageLinks)
    description: str = ""
    related_game_id: str | None = None


class WikiSection(OutputModel):
    """A named article section preserving text and related item references."""

    title: str = ""
    text: str = ""
    items: list[ItemSummary] = Field(default_factory=list)


class WikiPage(OutputModel):
    """Article information separate from any rendered page or template."""

    summary: WikiSummary
    illustration: ImageLinks = Field(default_factory=ImageLinks)
    skills: list[Skill] = Field(default_factory=list)
    talents: TalentTree = Field(default_factory=TalentTree)
    sections: list[WikiSection] = Field(default_factory=list)
