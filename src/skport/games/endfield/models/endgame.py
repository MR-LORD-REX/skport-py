"""Event, contract, and team records shared by endgame card families."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from skport.games.endfield.models.base import ModelIssue, OutputModel
from skport.games.endfield.models.identity import PlayerIdentity
from skport.games.endfield.models.images import CharacterImages, ImageLinks, SemanticLabel
from skport.games.endfield.models.item import ItemSummary, MedalSummary
from skport.games.endfield.models.progress import ResourceMeter


class TeamMember(OutputModel):
    """A battle participant without embedding a complete unrelated build."""

    character_id: str = ""
    template_id: int | None = None
    name: str = ""
    level: int | None = Field(default=None, ge=0)
    rarity: int | None = Field(default=None, ge=0)
    potential: int | None = Field(default=None, ge=0)
    position: int | None = Field(default=None, ge=0)
    element: SemanticLabel = Field(default_factory=SemanticLabel)
    profession: SemanticLabel = Field(default_factory=SemanticLabel)
    images: CharacterImages = Field(default_factory=CharacterImages)
    evolution: int | None = Field(default=None, ge=0)


class EnemySummary(ItemSummary):
    """A named stage enemy with artwork, level and ability text."""

    level: int | None = Field(default=None, ge=0)
    ability: str | None = None


class StageRun(OutputModel):
    """One clear attempt with time, team and optional contract scoring."""

    id: str = ""
    duration_seconds: float | None = Field(default=None, ge=0)
    completed_at: datetime | None = None
    completed: bool = False
    score: int | None = None
    waves: int | None = Field(default=None, ge=0)
    is_best: bool = False
    team: list[TeamMember] = Field(default_factory=list)


class EventStage(OutputModel):
    """Normal and hard records for one stage, keeping missing records explicit."""

    id: str = ""
    name: str = ""
    recommended_level: int | None = Field(default=None, ge=0)
    enemies: list[EnemySummary] = Field(default_factory=list)
    normal: StageRun | None = None
    hard: StageRun | None = None
    normal_cleared: bool = False
    hard_cleared: bool = False
    normal_id: str | None = None
    hard_id: str | None = None


class MonumentEvent(OutputModel):
    """An event's artwork, rules, medal and individual stages."""

    id: str = ""
    name: str = ""
    poster: ImageLinks = Field(default_factory=ImageLinks)
    medal: MedalSummary | None = None
    rules: list[str] = Field(default_factory=list)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool = False
    stages: list[EventStage] = Field(default_factory=list)


class MonumentState(OutputModel):
    """Player monument progress across independently inspectable events."""

    player: PlayerIdentity
    events: list[MonumentEvent] = Field(default_factory=list)
    snapshot_at: datetime | None = None
    issues: list[ModelIssue] = Field(default_factory=list)


class ContractModifier(OutputModel):
    """A contract indicator or buff with its score and unlock state."""

    id: str = ""
    name: str = ""
    description: str = ""
    icon: ImageLinks = Field(default_factory=ImageLinks)
    score: int = 0
    is_unlocked: bool = False
    params: dict[str, Any] = Field(default_factory=dict)


class CrisisContract(OutputModel):
    """One contract with summary progression and detailed runs when provided."""

    id: str = ""
    name: str = ""
    poster: ImageLinks = Field(default_factory=ImageLinks)
    medal: MedalSummary | None = None
    best_score: int = 0
    attempts: int = Field(default=0, ge=0)
    missions: list[ResourceMeter] = Field(default_factory=list)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    runs: list[StageRun] = Field(default_factory=list)
    modifiers: list[ContractModifier] = Field(default_factory=list)
    enemies: list[EnemySummary] = Field(default_factory=list)
    ends_at_collection: datetime | None = None
    rules: str = ""
    stage_id: str | None = None
    stage_name: str = ""
    stage_recommended_level: int | None = Field(default=None, ge=0)


class ContractState(OutputModel):
    """Current and historical contracts associated with one player."""

    player: PlayerIdentity
    current: CrisisContract | None = None
    contracts: list[CrisisContract] = Field(default_factory=list)
    snapshot_at: datetime | None = None
    issues: list[ModelIssue] = Field(default_factory=list)
