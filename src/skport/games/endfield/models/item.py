"""Small item and medal summaries reusable across card families."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from skport.games.endfield.models.base import OutputModel
from skport.games.endfield.models.images import ImageLinks


class ItemSummary(OutputModel):
    """A named game item with stable identity and available icon sources."""

    id: str = ""
    template_id: int | str | None = None
    name: str = ""
    description: str = ""
    rarity: int | None = Field(default=None, ge=0)
    icon: ImageLinks = Field(default_factory=ImageLinks)


class MedalSummary(ItemSummary):
    """Medal progression and placement used by profile and event cards."""

    level: int = Field(default=0, ge=0)
    plated: bool = False
    slot: int | None = Field(default=None, ge=0)
    initial_icon: ImageLinks = Field(default_factory=ImageLinks)
    plated_icon: ImageLinks = Field(default_factory=ImageLinks)
    obtained_at: datetime | None = None
    category: str | None = None
