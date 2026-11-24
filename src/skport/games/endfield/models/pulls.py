"""Normalized pull records, pages and optional history-derived summaries."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from skport.games.endfield.models.base import ModelIssue, OutputModel
from skport.games.endfield.models.identity import PlayerIdentity
from skport.games.endfield.models.item import ItemSummary


class PullRecord(OutputModel):
    """One observed draw or gift with independent banner and item identity."""

    id: str = ""
    sequence_id: str = ""
    kind: str = ""
    item: ItemSummary = Field(default_factory=ItemSummary)
    banner_id: str = ""
    banner_name: str = ""
    rarity: int | None = Field(default=None, ge=0)
    pulled_at: datetime | None = None
    is_free: bool = False
    count: int = Field(default=1, ge=1)
    pity_at_drop: int | None = Field(default=None, ge=0)


class PullPage(OutputModel):
    """A normalized page that preserves the service continuation contract."""

    records: list[PullRecord] = Field(default_factory=list)
    has_more: bool = False
    next_cursor: str | None = None
    owner: PlayerIdentity | None = None


class BannerPity(OutputModel):
    """Only observed or explicitly calculated banner state, with unknown limits."""

    banner_id: str = ""
    name: str = ""
    current: int = Field(default=0, ge=0)
    hard_limit: int | None = Field(default=None, ge=0)
    featured_guarantee: int | None = Field(default=None, ge=0)
    total: int = Field(default=0, ge=0)


class PullTotals(OutputModel):
    """Counts for the supplied history window, independent from pity totals."""

    character_draws: int = Field(default=0, ge=0)
    weapon_draws: int = Field(default=0, ge=0)
    free_draws: int = Field(default=0, ge=0)
    six_star_draws: int = Field(default=0, ge=0)


class PullHistory(OutputModel):
    """Records and optional pity state without implying complete account history."""

    player: PlayerIdentity
    records: list[PullRecord] = Field(default_factory=list)
    pity: list[BannerPity] = Field(default_factory=list)
    totals: PullTotals = Field(default_factory=PullTotals)
    from_time: datetime | None = None
    to_time: datetime | None = None
    complete_history: bool = False
    issues: list[ModelIssue] = Field(default_factory=list)
