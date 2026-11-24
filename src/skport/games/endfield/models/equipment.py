"""Equipment slots and enhancement-aware stat lines for build cards."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, computed_field

from skport.games.endfield.models.base import OutputModel
from skport.games.endfield.models.images import ImageLinks
from skport.games.endfield.models.stats import StatModifier, StatUnit, format_percent


class EquipmentSlot(StrEnum):
    """Distinct equipment positions, including both accessory slots."""

    BODY = "body"
    ARMS = "arms"
    ACCESSORY1 = "accessory1"
    ACCESSORY2 = "accessory2"


class StatLine(OutputModel):
    """One visible affix, retaining all properties in a combined line."""

    name: str = ""
    value: float | None = None
    unit: StatUnit = StatUnit.NUMBER
    level: int = Field(default=0, ge=0)
    max_level: int = Field(default=3, ge=0)
    stat_ids: list[int] = Field(default_factory=list)
    formula: str = ""
    icon: ImageLinks = Field(default_factory=ImageLinks)
    effects: list[StatModifier] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def display(self) -> str | None:
        """Expose unit-aware display text without magnitude heuristics."""
        if self.value is None:
            return None
        if self.unit is StatUnit.FRACTION:
            return format_percent(self.value)
        if self.unit is StatUnit.FACTOR:
            return f"{self.value:g}×"
        return f"{self.value:g}"


class Equipment(OutputModel):
    """An equipped piece with a canonical template when resolution succeeds."""

    slot: EquipmentSlot
    id: str = ""
    template_id: int | None = Field(default=None, gt=0)
    name: str = ""
    rarity: int = Field(default=0, ge=0)
    suit_id: int | str | None = None
    suit_name: str = ""
    icon: ImageLinks = Field(default_factory=ImageLinks)
    defense: float | None = None
    stat_lines: list[StatLine] = Field(default_factory=list)
    enhance_count: int = Field(default=0, ge=0)
    max_enhance: int | None = Field(default=None, ge=0)
