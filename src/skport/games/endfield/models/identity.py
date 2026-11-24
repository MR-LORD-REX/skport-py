"""Distinct public, game, and canonical character identities."""

from __future__ import annotations

from pydantic import Field

from skport.games.endfield.models.base import OutputModel


class CharacterIdentity(OutputModel):
    """Keep the SKPORT opaque ID alongside optional canonical Enka IDs."""

    skport_id: str = Field(min_length=1)
    template_id: int | None = Field(default=None, gt=0)
    str_id: str | None = None
    display_template_id: int | None = Field(default=None, gt=0)
    display_str_id: str | None = None


class PlayerIdentity(OutputModel):
    """Identify a social profile independently from its selected game role."""

    skport_id: str
    game_uid: str | None = None
    server_id: str | None = None
    name: str = ""
