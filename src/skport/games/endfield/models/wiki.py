"""Wiki information reusable by guide and operator-reference card layouts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from skport.games.endfield.models.base import ModelIssue, OutputModel
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
    locale: str | None = None
    tags: list[SemanticLabel] = Field(default_factory=list)
    dot_type: str | None = None


class WikiItemRef(OutputModel):
    """A wiki item link with its own ID, even when its summary is unavailable."""

    id: str
    count: int | None = Field(default=None, ge=0)
    display_type: str | None = None
    item: ItemSummary | None = None


class WikiTableCell(OutputModel):
    """An ordered cell with all of its text, illustrations, and links."""

    row_id: str
    column_id: str
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    blocks: list[WikiBlock] = Field(default_factory=list)


class WikiBlock(OutputModel):
    """An article block with typed content and a fallback for new block kinds."""

    id: str = ""
    kind: Literal["text", "image", "table", "quote", "video", "separator", "unknown"] = "unknown"
    source_type: str = ""
    text: str = ""
    image: ImageLinks = Field(default_factory=ImageLinks)
    url: str | None = None
    item_refs: list[WikiItemRef] = Field(default_factory=list)
    children: list[WikiBlock] = Field(default_factory=list)
    rows: list[list[WikiTableCell | None]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WikiAudio(OutputModel):
    """One audio clip and its localized transcript when provided."""

    id: str = ""
    title: str = ""
    transcript: str = ""
    url: str | None = None


class WikiEntry(OutputModel):
    """One ordered widget entry, preserving its title, kind, and body."""

    id: str = ""
    name: str = ""
    kind: str = ""
    icon: ImageLinks = Field(default_factory=ImageLinks)
    illustration: ImageLinks = Field(default_factory=ImageLinks)
    description: str = ""
    text: str = ""
    intro_blocks: list[WikiBlock] = Field(default_factory=list)
    blocks: list[WikiBlock] = Field(default_factory=list)
    audio: list[WikiAudio] = Field(default_factory=list)


class WikiField(OutputModel):
    """One labeled value from an article overview."""

    id: str = ""
    label: str = ""
    value: str = ""


class WikiSection(OutputModel):
    """A named article section preserving text and related item references."""

    title: str = ""
    text: str = ""
    items: list[ItemSummary] = Field(default_factory=list)
    id: str = ""
    chapter_id: str = ""
    chapter: str = ""
    kind: str = ""
    entries: list[WikiEntry] = Field(default_factory=list)
    fields: list[WikiField] = Field(default_factory=list)


class WikiPage(OutputModel):
    """Article information separate from any rendered page or template."""

    summary: WikiSummary
    illustration: ImageLinks = Field(default_factory=ImageLinks)
    skills: list[Skill] = Field(default_factory=list)
    talents: TalentTree = Field(default_factory=TalentTree)
    sections: list[WikiSection] = Field(default_factory=list)
    quote: str = ""
    bio: str = ""
    info_fields: list[WikiField] = Field(default_factory=list)
    skill_entries: list[WikiEntry] = Field(default_factory=list)
    lore: list[WikiEntry] = Field(default_factory=list)
    issues: list[ModelIssue] = Field(default_factory=list)
