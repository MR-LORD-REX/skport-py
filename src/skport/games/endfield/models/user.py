"""Verified SKPORT social information and the selected Endfield game identity."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from skport.games.endfield.models.base import OutputModel


class VerifiedUser(OutputModel):
    """Return social and in-game names separately, without account credentials."""

    skport_id: str = Field(min_length=1)
    skport_username: str
    game_uid: str = Field(min_length=1)
    in_game_name: str
    server_id: str = Field(min_length=1)
    server_name: str = ""
    source_scope: Literal["public", "owner"]
