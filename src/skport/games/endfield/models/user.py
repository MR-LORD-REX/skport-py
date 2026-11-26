"""SKPORT social profiles and verified Endfield game identities."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from skport.games.endfield.models.base import OutputModel
from skport.games.endfield.models.images import ImageLinks


class SocialProfileCounts(OutputModel):
    """Published community counters, with missing values kept separate from zero."""

    following: int | None = Field(default=None, ge=0)
    followers: int | None = Field(default=None, ge=0)
    likes_received: int | None = Field(default=None, ge=0)


class SocialProfilePendant(OutputModel):
    """The attached SKPORT social-profile decoration."""

    id: int | None = None
    title: str = ""
    description: str = ""
    icon: ImageLinks = Field(default_factory=ImageLinks)


class SocialProfile(OutputModel):
    """Community display metadata for a SKPORT ID."""

    skport_id: str = Field(min_length=1)
    skport_username: str
    biography: str = ""
    avatar: ImageLinks = Field(default_factory=ImageLinks)
    avatar_code: int | None = None
    gender_code: int | None = None
    status_code: int | None = None
    operation_status_code: int | None = None
    identity_code: int | None = None
    kind_code: int | None = None
    created_at: datetime | None = None
    last_login_at: datetime | None = None
    pendant: SocialProfilePendant | None = None
    counts: SocialProfileCounts = Field(default_factory=SocialProfileCounts)


class VerifiedUser(OutputModel):
    """Return social and in-game names separately, without account credentials."""

    skport_id: str = Field(min_length=1)
    skport_username: str
    game_uid: str = Field(min_length=1)
    in_game_name: str
    server_id: str = Field(min_length=1)
    server_name: str = ""
    source_scope: Literal["public", "owner"]
