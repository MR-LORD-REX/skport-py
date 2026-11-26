"""Discovery responses and exact wiki identity lookups."""

from __future__ import annotations

from pydantic import Field

from skport.games.endfield.models.base import ModelIssue, OutputModel
from skport.games.endfield.models.images import SemanticLabel
from skport.games.endfield.models.wiki import WikiSummary, WikiTag


class WikiCategory(SemanticLabel):
    """A main category or subcategory from the localized catalog."""

    parent_id: str | None = None
    position: int | None = None
    style: int | None = None
    status: int | None = None
    subcategories: list[WikiCategory] = Field(default_factory=list)
    filters: list[WikiTag] = Field(default_factory=list)


class WikiCatalogTree(OutputModel):
    """The wiki's ordered category and filter vocabulary."""

    locale: str
    categories: list[WikiCategory] = Field(default_factory=list)


class WikiIndex(OutputModel):
    """Summaries keyed by article ID with category-scoped game ID lookup."""

    locale: str
    items: dict[str, WikiSummary] = Field(default_factory=dict)
    issues: list[ModelIssue] = Field(default_factory=list)

    def by_game_id(
        self, game_id: str | int, *, type_sub_id: str | int, type_main_id: str | int = 1
    ) -> list[WikiSummary]:
        """Return every candidate so a caller can handle ambiguous associations."""
        return [
            summary
            for summary in self.items.values()
            if summary.main_type_id == str(type_main_id)
            and summary.sub_type_id == str(type_sub_id)
            and summary.related_game_id == str(game_id)
        ]


class WikiBatchResult(WikiIndex):
    """The summaries present in a batch and the requested IDs the service omitted."""

    requested_ids: list[str] = Field(default_factory=list)
    missing_ids: list[str] = Field(default_factory=list)
    main_categories: dict[str, WikiCategory] = Field(default_factory=dict)
    subcategories: dict[str, WikiCategory] = Field(default_factory=dict)
