"""Wiki information reusable by guide and operator-reference card layouts."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from skport.games.endfield.models.base import ModelIssue, OutputModel
from skport.games.endfield.models.images import ImageLinks, SemanticLabel
from skport.games.endfield.models.item import ItemSummary
from skport.games.endfield.models.skills import Skill
from skport.games.endfield.models.talents import TalentTree


class WikiAssociation(OutputModel):
    """A link published by the wiki from an article to a game entity."""

    game_id: str
    kind: str = ""
    name: str = ""
    dot_type: str | None = None


class WikiTag(SemanticLabel):
    """A catalog filter or leaf with its published semantic value."""

    value: str = ""
    type: int | None = None
    hidden: bool | None = None
    group_id: str | None = None
    children: list[WikiTag] = Field(default_factory=list)


class WikiSummary(OutputModel):
    """One catalog record with its identity, classification and artwork."""

    id: str
    name: str = ""
    category: SemanticLabel = Field(default_factory=SemanticLabel)
    icon: ImageLinks = Field(default_factory=ImageLinks)
    description: str = ""
    caption: list[WikiInline] = Field(default_factory=list)
    related_game_id: str | None = None
    locale: str | None = None
    tags: list[SemanticLabel] = Field(default_factory=list)
    dot_type: str | None = None
    main_type_id: str | None = None
    sub_type_id: str | None = None
    main_category: SemanticLabel = Field(default_factory=SemanticLabel)
    association: WikiAssociation | None = None
    facets: list[WikiTag] = Field(default_factory=list)
    redirect_url: str | None = None
    mobile_redirect_url: str | None = None
    hide_detail_cover: bool = False
    status: int | None = None
    published_at: datetime | None = None
    last_audit_passed_at: datetime | None = None


class WikiItemRef(OutputModel):
    """A wiki item link with its own ID, even when its summary is unavailable."""

    id: str
    count: int | None = Field(default=None, ge=0)
    display_type: str | None = None
    item: ItemSummary | None = None


class WikiInline(OutputModel):
    """One inline element with its display text, formatting, and references."""

    kind: Literal["text", "entry", "link", "pronunciation", "unknown"]
    source_type: str = ""
    text: str = ""
    reference: WikiItemRef | None = None
    url: str | None = None
    reading: str | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WikiCellSource(OutputModel):
    """Location of a value in the published article."""

    article_id: str
    locale: str | None = None
    section_id: str
    entry_id: str
    block_id: str
    row_id: str = ""
    column_id: str = ""


class WikiTableCell(OutputModel):
    """An ordered cell with all of its text, illustrations, and links."""

    row_id: str
    column_id: str
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    background_color: str | None = None
    vertical_align: str | None = None
    blocks: list[WikiBlock] = Field(default_factory=list)

    @property
    def text(self) -> str:
        """Return the readable text of the cell's blocks."""
        return "\n".join(block.text for block in self.blocks).strip()

    @property
    def item_refs(self) -> list[WikiItemRef]:
        """Read references in document order, including nested blocks."""
        return [ref for root in self.blocks for block in root.walk() for ref in block.item_refs]


class WikiListItem(OutputModel):
    """One item in a list, including its nested content."""

    id: str
    blocks: list[WikiBlock] = Field(default_factory=list)

    @property
    def text(self) -> str:
        """Return the readable content of the list item."""
        return "\n".join(block.text for block in self.blocks).strip()


class WikiBlock(OutputModel):
    """An article block with typed content and a fallback for new block kinds."""

    id: str = ""
    kind: Literal["text", "image", "table", "list", "quote", "video", "separator", "unknown"] = "unknown"
    source_type: str = ""
    text: str = ""
    image: ImageLinks = Field(default_factory=ImageLinks)
    url: str | None = None
    runs: list[WikiInline] = Field(default_factory=list)
    item_refs: list[WikiItemRef] = Field(default_factory=list)
    children: list[WikiBlock] = Field(default_factory=list)
    list_kind: str | None = None
    list_items: list[WikiListItem] = Field(default_factory=list)
    row_ids: list[str] = Field(default_factory=list)
    column_ids: list[str] = Field(default_factory=list)
    row_header: bool | None = None
    column_header: bool | None = None
    rows: list[list[WikiTableCell | None]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def walk(self) -> Iterator[WikiBlock]:
        """Yield the block and its descendants in document order."""
        yield self
        for block in self.children:
            yield from block.walk()
        for item in self.list_items:
            for block in item.blocks:
                yield from block.walk()
        for row in self.rows:
            for cell in row:
                if cell is not None:
                    for block in cell.blocks:
                        yield from block.walk()


class WikiAudio(OutputModel):
    """One audio clip and its localized transcript when provided."""

    id: str = ""
    title: str = ""
    transcript: str = ""
    url: str | None = None


class WikiEntry(OutputModel):
    """One ordered widget entry, preserving its title, kind, and body."""

    id: str = ""
    title: str = ""
    name: str = ""
    kind: str = ""
    icon: ImageLinks = Field(default_factory=ImageLinks)
    illustration: ImageLinks = Field(default_factory=ImageLinks)
    description: str = ""
    text: str = ""
    intro_blocks: list[WikiBlock] = Field(default_factory=list)
    intro_id: str = ""
    blocks: list[WikiBlock] = Field(default_factory=list)
    content_id: str = ""
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
    description_blocks: list[WikiBlock] = Field(default_factory=list)
    info_fields: list[WikiField] = Field(default_factory=list)
    skill_entries: list[WikiEntry] = Field(default_factory=list)
    lore: list[WikiEntry] = Field(default_factory=list)
    issues: list[ModelIssue] = Field(default_factory=list)


class WikiMaterialRecipe(OutputModel):
    """One published recipe row with its inputs, outputs, and source."""

    section_id: str
    entry_id: str
    table_id: str
    row_id: str
    name: str = ""
    requirement: str = ""
    requirement_label: str = ""
    inputs: list[WikiItemRef] = Field(default_factory=list)
    outputs: list[WikiItemRef] = Field(default_factory=list)


class WikiMaterial(OutputModel):
    """Published acquisition, usage, and recipes for an item."""

    summary: WikiSummary
    acquisition: list[WikiSection] = Field(default_factory=list)
    usage: list[WikiSection] = Field(default_factory=list)
    recipe_sections: list[WikiSection] = Field(default_factory=list)
    recipes: list[WikiMaterialRecipe] = Field(default_factory=list)
    issues: list[ModelIssue] = Field(default_factory=list)
