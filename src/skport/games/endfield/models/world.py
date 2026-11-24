"""Regional progression and factory information without layout-specific fields."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from skport.games.endfield.models.base import OutputModel
from skport.games.endfield.models.identity import PlayerIdentity
from skport.games.endfield.models.item import ItemSummary
from skport.games.endfield.models.progress import ResourceMeter


class AreaProgress(OutputModel):
    """Exploration counters for one area, retaining category-level detail."""

    id: str = ""
    name: str = ""
    counters: list[ResourceMeter] = Field(default_factory=list)


class Settlement(OutputModel):
    """A settlement's progression, stock and assigned operator."""

    id: str = ""
    name: str = ""
    level: int = Field(default=0, ge=0)
    experience: ResourceMeter = Field(default_factory=ResourceMeter)
    stock: ResourceMeter = Field(default_factory=ResourceMeter)
    officer: ItemSummary | None = None
    maximum_level: bool = False
    last_tick_at: datetime | None = None


class RegionProgress(OutputModel):
    """One world's region with funds, settlements and exploration."""

    id: str = ""
    name: str = ""
    level: int = Field(default=0, ge=0)
    funds: ResourceMeter = Field(default_factory=ResourceMeter)
    settlements: list[Settlement] = Field(default_factory=list)
    areas: list[AreaProgress] = Field(default_factory=list)
    factory: dict[str, Any] | None = None


class CrewMember(ItemSummary):
    """An assigned operator with source-provided stamina and favorability."""

    physical_strength: float | None = None
    favorability: float | None = None


class Cabin(OutputModel):
    """A spaceship cabin and its assigned crew."""

    id: str = ""
    name: str = ""
    level: int = Field(default=0, ge=0)
    crew: list[CrewMember] = Field(default_factory=list)
    kind: int | None = None
    reports: dict[str, Any] = Field(default_factory=dict)


class FactoryState(OutputModel):
    """World and spaceship state suitable for independent factory card layouts."""

    player: PlayerIdentity
    regions: list[RegionProgress] = Field(default_factory=list)
    cabins: list[Cabin] = Field(default_factory=list)
    snapshot_at: datetime | None = None
