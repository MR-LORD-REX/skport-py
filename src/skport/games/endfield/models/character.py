"""Character summaries and resolved builds independent of card templates."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from skport.games.endfield.models.base import ModelIssue, OutputModel
from skport.games.endfield.models.equipment import Equipment
from skport.games.endfield.models.equipment_set import EquipmentSet
from skport.games.endfield.models.identity import CharacterIdentity, PlayerIdentity
from skport.games.endfield.models.images import CharacterImages, SemanticLabel
from skport.games.endfield.models.item import ItemSummary
from skport.games.endfield.models.skills import Skill
from skport.games.endfield.models.stats import StatBlock, StatModifier
from skport.games.endfield.models.talents import TalentTree
from skport.games.endfield.models.weapon import Weapon


class BuildStatus(StrEnum):
    """Whether canonical build information is complete or still partial."""

    COMPLETE = "complete"
    PARTIAL = "partial"


class CalculationState(StrEnum):
    """Differentiate omitted calculation from a missing canonical dependency."""

    CALCULATED = "calculated"
    UNAVAILABLE = "unavailable"
    NOT_REQUESTED = "not_requested"


class CharacterSummary(OutputModel):
    """The identity, artwork and progression required by profile/roster tiles."""

    identity: CharacterIdentity
    name: str = ""
    level: int = Field(default=1, ge=1)
    max_level: int = Field(default=90, ge=1)
    evolution: int = Field(default=0, ge=0)
    potential: int = Field(default=0, ge=0)
    rarity: int = Field(default=0, ge=0)
    element: SemanticLabel = Field(default_factory=SemanticLabel)
    profession: SemanticLabel = Field(default_factory=SemanticLabel)
    weapon_type: SemanticLabel = Field(default_factory=SemanticLabel)
    images: CharacterImages = Field(default_factory=CharacterImages)
    showcase_index: int | None = Field(default=None, ge=0)


class CharacterBuild(CharacterSummary):
    """Expose renderable SKPORT information and optional canonical calculation."""

    owner: PlayerIdentity | None = None
    stats: StatBlock | None = None
    skills: list[Skill] = Field(default_factory=list)
    talents: TalentTree = Field(default_factory=TalentTree)
    equipment: list[Equipment] = Field(default_factory=list)
    equipment_sets: list[EquipmentSet] = Field(default_factory=list)
    weapon: Weapon | None = None
    tactical_item: ItemSummary | None = None
    set_effects: list[StatModifier] = Field(default_factory=list)
    asset_revision: str | None = None
    locale: str = "en"
    status: BuildStatus = BuildStatus.PARTIAL
    calculation_state: CalculationState = CalculationState.NOT_REQUESTED
    issues: list[ModelIssue] = Field(default_factory=list)
    source_fields: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_equipment_slots(self) -> CharacterBuild:
        """Reject duplicate positions without requiring four equipped pieces."""
        slots = [piece.slot for piece in self.equipment]
        if len(slots) != len(set(slots)):
            raise ValueError("each equipment slot can contain only one piece")
        if self.calculation_state is CalculationState.CALCULATED and self.stats is None:
            raise ValueError("a calculated build must include statistics")
        return self
