"""Normalize SKPORT social profiles and verification responses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import ValidationError

from skport.config import ImageSource
from skport.errors import DecodeError
from skport.games.endfield.clean.common import image_links, timestamp, wire_object
from skport.games.endfield.identity import Role
from skport.games.endfield.models.user import (
    SocialProfile,
    SocialProfileCounts,
    SocialProfilePendant,
    VerifiedUser,
)


def _social_fields(
    data: Any, expected_id: str | None,
) -> tuple[Mapping[str, Any], Mapping[str, Any], str, str]:
    if not isinstance(data, Mapping) or not isinstance(data.get("user"), Mapping):
        raise DecodeError("social profile must contain a user object")
    user = data["user"]
    basic = user.get("basicUser")
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
    return user, basic, normalized_id, username


def _counter(value: Any, field: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, str)) and not isinstance(value, bool) and str(value).isdecimal():
        return int(value)
    raise DecodeError(f"social profile counter {field} must be a nonnegative integer")


def build_social_profile(
    data: Any,
    preferred: ImageSource = ImageSource.SKPORT,
    *,
    expected_id: str | None = None,
) -> SocialProfile:
    """Read the published social fields from a decoded SKPORT user response."""
    user, basic, social_id, username = _social_fields(data, expected_id)
    pendant_data = user.get("pendant")
    if pendant_data is not None:
        pendant_data = wire_object(pendant_data, "social profile pendant")
    counts_data = data.get("userRts")
    counts = {} if counts_data is None else wire_object(counts_data, "social profile counters")
    try:
        pendant = SocialProfilePendant(
            id=pendant_data.get("id"),
            title=pendant_data.get("title") or "",
            description=pendant_data.get("description") or "",
            icon=image_links(pendant_data.get("iconUrl"), preferred=preferred),
        ) if pendant_data else None
        return SocialProfile(
            skport_id=social_id,
            skport_username=username,
            biography=basic.get("profile") or "",
            avatar=image_links(basic.get("avatar"), preferred=preferred),
            avatar_code=basic.get("avatarCode"),
            gender_code=basic.get("gender"),
            status_code=basic.get("status"),
            operation_status_code=basic.get("operationStatus"),
            identity_code=basic.get("identity"),
            kind_code=basic.get("kind"),
            created_at=timestamp(basic.get("createdAt")),
            last_login_at=timestamp(basic.get("latestLoginAt")),
            pendant=pendant,
            counts=SocialProfileCounts(
                following=_counter(counts.get("follow"), "follow"),
                followers=_counter(counts.get("fans"), "fans"),
                likes_received=_counter(counts.get("liked"), "liked"),
            ),
        )
    except ValidationError:
        raise DecodeError("social profile contains invalid display metadata") from None


def build_verified_user(
    data: Any,
    role: Role,
    scope: Literal["public", "owner"],
    *,
    expected_id: str | None = None,
) -> VerifiedUser:
    """Read the social profile's basicUser fields and the verified game binding."""
    _, _, normalized_id, username = _social_fields(data, expected_id)
    return VerifiedUser(
        skport_id=normalized_id,
        skport_username=username,
        game_uid=role.role_id,
        in_game_name=role.nickname,
        server_id=role.server_id,
        server_name=role.server_name,
        source_scope=scope,
    )
