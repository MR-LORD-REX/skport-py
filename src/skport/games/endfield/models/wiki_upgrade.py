"""Published wiki upgrade steps, cost observations, and selected material totals."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Literal

from pydantic import Field, computed_field

from skport.games.endfield.models.base import ModelIssue, OutputModel
from skport.games.endfield.models.images import ImageLinks
from skport.games.endfield.models.wiki import WikiCellSource, WikiSummary

WikiUpgradeKind = Literal["level", "promotion", "outfitting", "talent", "skill", "potential"]
WikiCostStatus = Literal["known", "none", "partial", "unknown"]


class WikiMaterialAmount(OutputModel):
    """A cited material and the published quantity when available."""

    wiki_id: str
    quantity: int | None = Field(default=None, ge=0)
    summary: WikiSummary | None = None
    sources: list[WikiCellSource] = Field(default_factory=list)


class WikiUpgradeCost(OutputModel):
    """One observed cost with any equivalent source cells grouped together."""

    status: WikiCostStatus = "unknown"
    materials: list[WikiMaterialAmount] = Field(default_factory=list)
    sources: list[WikiCellSource] = Field(default_factory=list)
    note: str = ""
    shared: bool = False


class WikiUpgradeStep(OutputModel):
    """One selectable milestone, skill rank, talent, or unlock."""

    id: str
    kind: WikiUpgradeKind
    label: str
    source: WikiCellSource
    costs: list[WikiUpgradeCost] = Field(default_factory=list)
    effect: str = ""
    requirements: list[str] = Field(default_factory=list)
    icon: ImageLinks = Field(default_factory=ImageLinks)
    from_level: int | None = Field(default=None, ge=1)
    to_level: int | None = Field(default=None, ge=1)
    rank: int | None = Field(default=None, ge=1)
    mastery: bool = False
    skill_id: str | None = None
    skill_name: str = ""
    skill_kind: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cost_status(self) -> WikiCostStatus | Literal["alternative"]:
        if len(self.costs) > 1:
            return "alternative"
        return self.costs[0].status if self.costs else "unknown"


class WikiUpgradeTotal(OutputModel):
    """Material totals for the selection, with any unpriced steps identified."""

    step_ids: list[str] = Field(default_factory=list)
    materials: list[WikiMaterialAmount] = Field(default_factory=list)
    unpriced_step_ids: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def complete(self) -> bool:
        return not self.unpriced_step_ids


class WikiUpgradeGuide(OutputModel):
    """Upgrade data from one article and one locale."""

    summary: WikiSummary
    requested_locale: str | None = None
    steps: list[WikiUpgradeStep] = Field(default_factory=list)
    missing_groups: list[WikiUpgradeKind] = Field(default_factory=list)
    issues: list[ModelIssue] = Field(default_factory=list)

    @property
    def material_ids(self) -> list[str]:
        """List the distinct material IDs referenced by the guide."""
        return list(dict.fromkeys(
            amount.wiki_id for step in self.steps for cost in step.costs for amount in cost.materials
        ))

    def total(
        self, step_ids: Iterable[str], *, cost_choices: Mapping[str, int] | None = None,
    ) -> WikiUpgradeTotal:
        """Sum selected observations. Use zero-based cost choices for conflicting recipes."""
        selected = list(dict.fromkeys(step_ids))
        choices = cost_choices or {}
        steps = {step.id: step for step in self.steps}
        unknown = set(selected).difference(steps)
        if unknown:
            raise ValueError(f"Unknown wiki upgrade step: {min(unknown)}")
        if choices.keys() - set(selected):
            raise ValueError("Cost choices must select previously selected upgrade steps")

        amounts: dict[str, WikiMaterialAmount] = {}
        unpriced: list[str] = []
        for step_id in selected:
            step = steps[step_id]
            choice = choices.get(step_id)
            cost: WikiUpgradeCost | None
            if choice is not None:
                if isinstance(choice, bool) or not isinstance(choice, int) or not 0 <= choice < len(step.costs):
                    raise ValueError(f"Invalid cost choice for wiki upgrade step: {step_id}")
                cost = step.costs[choice]
            else:
                cost = step.costs[0] if len(step.costs) == 1 else None
            if cost is None or cost.status in {"partial", "unknown"}:
                unpriced.append(step_id)
            if cost is None or cost.shared:
                continue
            for amount in cost.materials:
                if amount.quantity is None:
                    continue
                previous = amounts.get(amount.wiki_id)
                if previous is None:
                    amounts[amount.wiki_id] = amount.model_copy(deep=True)
                    continue
                previous.quantity = (previous.quantity or 0) + amount.quantity
                previous.summary = previous.summary or amount.summary
                previous.sources.extend(source for source in amount.sources if source not in previous.sources)

        return WikiUpgradeTotal(step_ids=selected, materials=list(amounts.values()), unpriced_step_ids=unpriced)
