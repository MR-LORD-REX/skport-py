"""Localized bulletin and game-enum output."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from skport.games.endfield.models.base import OutputModel
from skport.games.endfield.models.images import SemanticLabel


class EnumCatalog(OutputModel):
    """Keep enum groups and their stable keys alongside localized labels."""

    groups: dict[str, list[SemanticLabel]] = Field(default_factory=dict)
    locale: str = ""

    def label(self, group: str, key: str) -> SemanticLabel | None:
        """Find an enum entry within its group."""
        return next((entry for entry in self.groups.get(group, []) if entry.key == key), None)


class Notice(OutputModel):
    """A bulletin with display-ready content and an optional link."""

    id: str
    title: str = ""
    header: str = ""
    text: str = ""
    category: str = ""
    locale: str = ""
    published_at: datetime | None = None
    url: str | None = None
