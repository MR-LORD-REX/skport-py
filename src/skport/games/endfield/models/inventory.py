"""Owner inventory organized by item family and service identity."""

from __future__ import annotations

from pydantic import Field

from skport.games.endfield.models.base import OutputModel
from skport.games.endfield.models.item import ItemSummary


class InventoryEntry(ItemSummary):
    """An inventory item with independent ownership and quantity evidence."""

    owned: bool | None = None
    count: int | None = Field(default=None, ge=0)


class InventorySkill(OutputModel):
    """An observed inventory skill form and its progression."""

    id: str
    level: int = Field(ge=0)
    form: str = ""


class InventoryOperator(InventoryEntry):
    """An operator and the progression observed in the owner's inventory."""

    level: int | None = Field(default=None, ge=0)
    evolution: int | None = Field(default=None, ge=0)
    potential: int | None = Field(default=None, ge=0)
    gender: str = ""
    skills: dict[str, InventorySkill] = Field(default_factory=dict)


class Inventory(OutputModel):
    """Owner-scoped inventory with separate category maps."""

    game_uid: str = ""
    server_id: str = ""
    game_level: int | None = Field(default=None, ge=0)
    gender: str = ""
    operators: dict[str, InventoryOperator] = Field(default_factory=dict)
    weapons: dict[str, InventoryEntry] = Field(default_factory=dict)
    equipment: dict[str, InventoryEntry] = Field(default_factory=dict)
    tactical_items: dict[str, InventoryEntry] = Field(default_factory=dict)
