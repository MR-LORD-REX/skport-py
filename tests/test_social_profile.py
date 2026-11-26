"""Contract for the community profile response, independent of game cards."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from skport.config import ImageSource
from skport.errors import DecodeError
from skport.games.endfield.clean.user import build_social_profile


def test_social_profile_uses_observed_public_api_keys() -> None:
    payload = {
        "user": {
            "basicUser": {
                "id": "1234",
                "nickname": "Community user",
                "profile": "About me",
                "avatar": "https://example.test/avatar.png",
                "avatarCode": 0,
                "gender": 1,
                "status": 0,
                "operationStatus": 0,
                "identity": 2,
                "kind": 0,
                "createdAt": "1765324800",
                "latestLoginAt": "0",
            },
            "pendant": {
                "id": 44,
                "iconUrl": "https://example.test/pendant.png",
                "title": "Community badge",
                "description": "A profile decoration",
            },
            "background": None,
        },
        "userRts": {"follow": "0", "fans": "11", "liked": "23"},
        "userSanctionList": [],
        "userInfoApply": {},
    }

    profile = build_social_profile(payload, ImageSource.ENKA, expected_id="1234")

    assert profile.skport_id == "1234" and profile.skport_username == "Community user"
    assert profile.biography == "About me"
    assert profile.avatar.url == "https://example.test/avatar.png"
    assert profile.avatar_code == profile.kind_code == 0
    assert profile.gender_code == 1
    assert profile.created_at == datetime.fromtimestamp(1765324800, UTC)
    assert profile.last_login_at is None
    assert profile.pendant is not None
    assert profile.pendant.id == 44
    assert profile.pendant.icon.url == "https://example.test/pendant.png"
    assert profile.counts.model_dump() == {"following": 0, "followers": 11, "likes_received": 23}
    assert profile.model_dump().get("userInfoApply") is None


def test_social_profile_leaves_missing_metadata_unset() -> None:
    profile = build_social_profile({"user": {"basicUser": {"id": 1234, "nickname": "User"}, "pendant": None}})

    assert profile.skport_id == "1234"
    assert profile.avatar.url is None
    assert profile.pendant is None
    assert profile.counts.model_dump() == {"following": None, "followers": None, "likes_received": None}


def test_social_profile_checks_the_requested_identity_and_counter_types() -> None:
    payload = {"user": {"basicUser": {"id": "1234", "nickname": "User"}}, "userRts": {"fans": True}}

    with pytest.raises(DecodeError, match="does not match"):
        build_social_profile(payload, expected_id="2222")
    with pytest.raises(DecodeError, match="counter fans"):
        build_social_profile(payload)
