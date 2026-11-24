"""Equipment set summaries shared by build and comparison card layouts."""

from __future__ import annotations

from pydantic import Field, computed_field

from skport.games.endfield.models.base import OutputModel
from skport.games.endfield.models.images import ImageLinks
from skport.games.endfield.models.stats import StatModifier


class EquipmentSet(OutputModel):
    """Keep observed set metadata separate from declared static modifiers."""

    id: str = ""
    template_id: str | None = None
    name: str = ""
    pieces: int = Field(default=0, ge=0)
    required_pieces: int = Field(default=3, ge=1)
    icon: ImageLinks = Field(default_factory=ImageLinks)
    description: str = ""
    effects: list[StatModifier] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def active(self) -> bool:
        """Whether the equipped piece count meets the set's activation threshold."""
        return self.pieces >= self.required_pieces
