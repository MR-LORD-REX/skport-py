"""Daily attendance status, rewards, and claim results."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from skport.games.endfield.models.base import OutputModel
from skport.games.endfield.models.item import ItemSummary


class AttendanceDay(OutputModel):
    """One monthly or first-time reward slot."""

    award_id: str
    available: bool
    done: bool


class AttendanceReward(ItemSummary):
    """Reward metadata shared by calendar days and claim results."""

    count: int = Field(ge=0)


class AttendanceAwardRef(OutputModel):
    """An ordered claim reference, including unfamiliar reward types."""

    id: str
    type: int


class AttendanceStatus(OutputModel):
    """A daily attendance snapshot for the selected owner."""

    current_at: datetime | None = None
    calendar: list[AttendanceDay] = Field(default_factory=list)
    first: list[AttendanceDay] = Field(default_factory=list)
    rewards_by_id: dict[str, AttendanceReward] = Field(default_factory=dict)
    has_today: bool

    @property
    def available_days(self) -> list[AttendanceDay]:
        """Return the slots marked available and still incomplete."""
        return [day for day in (*self.calendar, *self.first) if day.available and not day.done]


class CheckInResult(OutputModel):
    """The current and next claim rewards, in the service's order."""

    claimed_at: datetime | None = None
    awards: list[AttendanceAwardRef] = Field(default_factory=list)
    tomorrow_awards: list[AttendanceAwardRef] = Field(default_factory=list)
    rewards_by_id: dict[str, AttendanceReward] = Field(default_factory=dict)

    @property
    def rewards(self) -> list[AttendanceReward | None]:
        """Resolve each claimed reference without shifting unresolved positions."""
        return [self.rewards_by_id.get(ref.id) for ref in self.awards]

    @property
    def tomorrow_rewards(self) -> list[AttendanceReward | None]:
        """Resolve each referenced reward for the next claim."""
        return [self.rewards_by_id.get(ref.id) for ref in self.tomorrow_awards]
