"""Public character and weapon banner metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from skport.games.endfield.models.base import OutputModel
from skport.games.endfield.models.item import ItemSummary


class BannerItem(ItemSummary):
    """An item in a publicly listed banner and its service display marker."""

    dot_type: str | int | None = None
    link: str | None = None


class BannerWindow(OutputModel):
    """An optional banner schedule for one SKPORT region."""

    region: str
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class Banner(OutputModel):
    """A public listing with item metadata and regional release windows."""

    id: str
    kind: Literal["character", "weapon"]
    name: str = ""
    sort_id: int | None = None
    items: list[BannerItem] = Field(default_factory=list)
    windows: list[BannerWindow] = Field(default_factory=list)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
