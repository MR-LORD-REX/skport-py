"""Explicit stat units, formula inputs, and calculated property output."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from pydantic import Field, computed_field, model_validator

from skport.games.endfield.models.base import OutputModel
from skport.games.endfield.models.images import ImageLinks


class StatUnit(StrEnum):
    """Units are metadata, never inferred from the magnitude of a value."""

    FLAT = "flat"
    FRACTION = "fraction"
    FACTOR = "factor"
    NUMBER = "number"


def format_percent(value: float, places: int = 1) -> str:
    """Convert a fraction to percent text with deterministic decimal rounding."""
    if places < 0 or places > 12:
        raise ValueError("percent precision must be between zero and twelve")
    quantum = Decimal(1).scaleb(-places)
    amount = (Decimal(str(value)) * 100).quantize(quantum, rounding=ROUND_HALF_UP)
    return f"{amount:.{places}f}%"


class StatModifier(OutputModel):
    """One canonical modifier before calculation-stage aggregation."""

    id: int
    formula: str
    value: float
    unit: StatUnit = StatUnit.NUMBER


class StatValue(OutputModel):
    """A final property value and the metadata a card renderer requires."""

    id: int
    value: float
    unit: StatUnit = StatUnit.NUMBER
    name: str = ""
    icon: ImageLinks = Field(default_factory=ImageLinks)
    is_main: bool = False
    is_sub: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def display(self) -> str:
        """Format percentage fractions while keeping scalar and factor semantics."""
        if self.unit is StatUnit.FRACTION:
            return format_percent(self.value)
        if self.unit is StatUnit.FACTOR:
            return f"{self.value:g}×"
        return f"{self.value:g}"


class StatContribution(OutputModel):
    """Explain one source contribution without collapsing formula semantics."""

    stat_id: int
    source: str
    formula: str
    value: float
    source_id: str = ""


_STAT_NAMES = {
    "hp": 1,
    "attack": 2,
    "atk": 2,
    "defense": 3,
    "def": 3,
    "critical_rate": 9,
    "crit_rate": 9,
    "critical_damage": 10,
    "crit_damage": 10,
    "strength": 39,
    "agility": 40,
    "intellect": 41,
    "will": 42,
    "ultimate_gain": 44,
    "physical_damage": 50,
    "heat_damage": 51,
    "electric_damage": 52,
    "cryo_damage": 53,
    "nature_damage": 54,
    "ether_damage": 55,
    "arts_intensity": 87,
}


class StatBlock(OutputModel):
    """Preserve every calculated property, including unknown future IDs."""

    values: dict[int, StatValue] = Field(default_factory=dict)
    main_attribute: int | None = None
    sub_attribute: int | None = None
    contributions: list[StatContribution] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_property_keys(self) -> StatBlock:
        """Reject property dictionaries whose keys describe a different stat."""
        if any(property_id != stat.id for property_id, stat in self.values.items()):
            raise ValueError("stat dictionary keys must match property IDs")
        return self

    def value(self, property_id: int) -> float:
        """Return a known property's numeric value, or zero when absent."""
        stat = self.values.get(property_id)
        return stat.value if stat is not None else 0.0

    def percent(self, property_id: int | str, places: int = 1) -> str:
        """Format a known fractional property without guessing its units."""
        if isinstance(property_id, str):
            key = property_id.strip().casefold().replace(" ", "_")
            property_id = int(key) if key.isdecimal() else _STAT_NAMES.get(key, -1)
        stat = self.values.get(property_id)
        if stat is None:
            raise KeyError(property_id)
        if stat.unit is not StatUnit.FRACTION:
            raise ValueError("percent formatting requires a fraction property")
        return format_percent(stat.value, places)

    @property
    def hp(self) -> int:
        return int(self.value(1))

    @property
    def attack(self) -> int:
        return int(self.value(2))

    @property
    def defense(self) -> int:
        return int(self.value(3))

    @property
    def strength(self) -> int:
        return int(self.value(39))

    @property
    def agility(self) -> int:
        return int(self.value(40))

    @property
    def intellect(self) -> int:
        return int(self.value(41))

    @property
    def will(self) -> int:
        return int(self.value(42))

    @property
    def critical_rate(self) -> float:
        return self.value(9)

    @property
    def critical_damage(self) -> float:
        return self.value(10)

    @property
    def arts_intensity(self) -> int:
        return int(self.value(87))
