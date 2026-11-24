"""Talent nodes and potential unlocks without flattening distinct properties."""

from __future__ import annotations

from pydantic import Field, computed_field

from skport.games.endfield.models.base import OutputModel
from skport.games.endfield.models.images import ImageLinks
from skport.games.endfield.models.stats import StatModifier


class TalentNode(OutputModel):
    """One canonical talent node and its observed unlock state."""

    id: str
    name: str = ""
    kind: str = "combat"
    icon: ImageLinks = Field(default_factory=ImageLinks)
    locked_icon: ImageLinks = Field(default_factory=ImageLinks)
    level: int = Field(default=0, ge=0)
    max_level: int = Field(default=1, ge=0)
    unlocked: bool = False
    description: str = ""
    effects: list[StatModifier] = Field(default_factory=list)


class Potential(OutputModel):
    """One potential tier with all of its independent modifiers."""

    level: int = Field(ge=0)
    name: str = ""
    description: str = ""
    unlocked: bool = False
    effects: list[StatModifier] = Field(default_factory=list)


class TalentTree(OutputModel):
    """Keep nodes, potentials and original unlocked IDs available to renderers."""

    nodes: list[TalentNode] = Field(default_factory=list)
    potentials: list[Potential] = Field(default_factory=list)
    unlocked_node_ids: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def unlocked_count(self) -> int:
        return sum(node.unlocked or node.id in self.unlocked_node_ids for node in self.nodes)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_count(self) -> int:
        return len(self.nodes)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def progress(self) -> float:
        return self.unlocked_count / self.total_count if self.total_count else 0.0
