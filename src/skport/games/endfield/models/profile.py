"""Player information and ordered character collections for profile cards."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from skport.games.endfield.models.base import ModelIssue, OutputModel
from skport.games.endfield.models.character import CharacterBuild
from skport.games.endfield.models.identity import PlayerIdentity
from skport.games.endfield.models.images import ImageLinks
from skport.games.endfield.models.item import MedalSummary
from skport.games.endfield.models.world import RegionProgress


class OwnershipCounts(OutputModel):
    """Keep ownership totals distinct from the returned public character list."""

    characters: int = Field(default=0, ge=0)
    weapons: int = Field(default=0, ge=0)
    documents: int = Field(default=0, ge=0)
    achievements: int = Field(default=0, ge=0)


class ProfilePrivacy(OutputModel):
    """Represent source visibility signals without assuming absent flags are true."""

    card_visible: bool | None = None
    details_visible: bool | None = None
    character_visible: bool | None = None


class PlayerCard(OutputModel):
    """A normalized player snapshot with builds and image-source alternatives."""

    player: PlayerIdentity
    avatar: ImageLinks = Field(default_factory=ImageLinks)
    banner: ImageLinks = Field(default_factory=ImageLinks)
    biography: str = ""
    mission: str = ""
    authority_level: int = Field(default=0, ge=0)
    world_level: int = Field(default=0, ge=0)
    experience: int | None = Field(default=None, ge=0)
    counts: OwnershipCounts = Field(default_factory=OwnershipCounts)
    created_at: datetime | None = None
    snapshot_at: datetime | None = None
    server_time: datetime | None = None
    medals: list[MedalSummary] = Field(default_factory=list)
    characters: list[CharacterBuild] = Field(default_factory=list)
    showcase_ids: list[str] = Field(default_factory=list)
    privacy: ProfilePrivacy = Field(default_factory=ProfilePrivacy)
    regions: list[RegionProgress] = Field(default_factory=list)
    asset_revision: str | None = None
    locale: str = "en"
    issues: list[ModelIssue] = Field(default_factory=list)
    server_name: str | None = None
    last_login_at: datetime | None = None
    modules: list[Any] = Field(default_factory=list)
    visibility: dict[str, Any] = Field(default_factory=dict)
    source_scope: Literal["public", "owner"] = "public"
    roster_complete: bool | None = None
