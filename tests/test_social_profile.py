"""Contract for the community profile response, independent of game cards."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from skport import SkportClient
from skport.config import ImageSource
from skport.errors import DecodeError
from skport.games.endfield.clean.user import build_social_profile
from skport.games.endfield.models import PlayerCard, PlayerIdentity, SocialProfile


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


async def test_skport_profile_returns_typed_social_data_with_client_image_preference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "user": {
            "basicUser": {
                "id": 1234,
                "nickname": "Community user",
                "avatar": "https://example.test/avatar.png",
            },
            "pendant": {"id": 44, "iconUrl": "https://example.test/pendant.png"},
        },
        "userRts": {"fans": "11"},
    }
    async with SkportClient(tokens=["viewer"], icon_source=ImageSource.ENKA) as client:
        read = AsyncMock(return_value=payload)
        card_read = AsyncMock(side_effect=AssertionError("Social profiles do not fetch game cards"))
        binding_read = AsyncMock(side_effect=AssertionError("Social profiles do not fetch game bindings"))
        monkeypatch.setattr(client.api, "user", read)
        monkeypatch.setattr(client.api, "binding", binding_read)
        monkeypatch.setattr(client.endfield, "card", card_read)

        result = await client.endfield.skport_profile("  1234  ", lang="ja")

    assert isinstance(result, SocialProfile)
    assert result.skport_id == "1234" and result.skport_username == "Community user"
    assert result.avatar.preferred is ImageSource.ENKA
    assert result.avatar.url == "https://example.test/avatar.png"
    assert result.pendant is not None and result.pendant.icon.preferred is ImageSource.ENKA
    assert result.counts.followers == 11
    read.assert_awaited_once()
    assert read.await_args is not None
    assert str(read.await_args.kwargs["skport_id"]).strip() == "1234"
    assert read.await_args.kwargs["lang"] == "ja"
    assert read.await_args.kwargs.get("token") is None
    card_read.assert_not_awaited()
    binding_read.assert_not_awaited()


async def test_skport_profile_raw_preserves_decoded_response_and_typed_validates_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"user": {"basicUser": {"id": "other", "nickname": "Another user"}}, "futureField": True}
    async with SkportClient(tokens=["viewer"]) as client:
        monkeypatch.setattr(client.api, "user", AsyncMock(return_value=payload))

        assert await client.endfield.skport_profile(skport_id=1234, raw=True) is payload
        with pytest.raises(DecodeError, match="does not match"):
            await client.endfield.skport_profile(1234)


@pytest.mark.parametrize("raw", [False, True])
async def test_profile_delegates_to_game_card_with_all_selections(
    monkeypatch: pytest.MonkeyPatch,
    raw: bool,
) -> None:
    card = PlayerCard(player=PlayerIdentity(skport_id="1234", game_uid="game-role", server_id="2"))
    payload = {"detail": {"base": {"roleId": "game-role"}}, "futureField": True}
    expected = payload if raw else card
    async with SkportClient(tokens=["viewer"]) as client:
        read = AsyncMock(return_value=expected)
        social_read = AsyncMock(side_effect=AssertionError("Game profiles delegate to card"))
        monkeypatch.setattr(client.endfield, "card", read)
        monkeypatch.setattr(client.api, "user", social_read)

        if raw:
            result = await client.endfield.profile(
                skport_id=1234, role_id=42, server_id=2, lang="ko", raw=True
            )
        else:
            result = await client.endfield.profile(1234, role_id=42, server_id=2, lang="ko")

    assert result is expected
    read.assert_awaited_once()
    assert read.await_args is not None
    forwarded = read.await_args.kwargs.copy()
    forwarded_id = read.await_args.args[0] if read.await_args.args else forwarded.pop("skport_id")
    assert forwarded_id == 1234
    assert forwarded == {"role_id": 42, "server_id": 2, "lang": "ko", "raw": raw}
    social_read.assert_not_awaited()
