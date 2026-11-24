"""Resource and activity state measured against SKPORT's server clock."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, computed_field

from skport.config import ImageSource
from skport.games.endfield.models.base import OutputModel
from skport.games.endfield.models.identity import PlayerIdentity


class ResourceMeter(OutputModel):
    """Preserve actual current/maximum values, including permitted overflow."""

    key: str = ""
    name: str = ""
    current: float = Field(default=0, ge=0)
    maximum: float = Field(default=0, ge=0)
    recovery_at: datetime | None = None
    refresh_at: datetime | None = None
    note: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ratio(self) -> float:
        """Expose the true ratio; a renderer may clamp its progress bar."""
        return self.current / self.maximum if self.maximum else 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def complete(self) -> bool:
        return self.maximum > 0 and self.current >= self.maximum


class LiveStatus(OutputModel):
    """Player resources and activity progression at a known source timestamp."""

    player: PlayerIdentity
    server_time: datetime | None = None
    sanity: ResourceMeter | None = None
    daily: ResourceMeter | None = None
    weekly: ResourceMeter | None = None
    battle_pass: ResourceMeter | None = None
    credits: ResourceMeter | None = None
    activities: list[ResourceMeter] = Field(default_factory=list)
    current_event: dict[str, Any] = Field(default_factory=dict)
    preferred_image_source: ImageSource = ImageSource.SKPORT
