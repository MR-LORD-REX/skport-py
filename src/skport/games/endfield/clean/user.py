"""Normalize verification responses without fetching player cards or assets."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from skport.errors import DecodeError
from skport.games.endfield.identity import Role
from skport.games.endfield.models.user import VerifiedUser


def build_verified_user(
    data: Any,
    role: Role,
    scope: Literal["public", "owner"],
    *,
    expected_id: str | None = None,
) -> VerifiedUser:
    """Read the social profile's basicUser fields and the verified game binding."""
    if not isinstance(data, Mapping) or not isinstance(data.get("user"), Mapping):
        raise DecodeError("social profile must contain a user object")
    basic = data["user"].get("basicUser")
    if not isinstance(basic, Mapping):
        raise DecodeError("social profile must contain a basicUser object")
    social_id = basic.get("id")
    username = basic.get("nickname")
    if not isinstance(social_id, (str, int)) or isinstance(social_id, bool) or not str(social_id).strip():
        raise DecodeError("social profile must contain a nonempty SKPORT ID")
    if not isinstance(username, str):
        raise DecodeError("social profile must contain a SKPORT nickname")
    normalized_id = str(social_id).strip()
    if expected_id is not None and normalized_id != expected_id:
        raise DecodeError("social profile does not match the requested SKPORT ID")
    return VerifiedUser(
        skport_id=normalized_id,
        skport_username=username,
        game_uid=role.role_id,
        in_game_name=role.nickname,
        server_id=role.server_id,
        server_name=role.server_name,
        source_scope=scope,
    )
