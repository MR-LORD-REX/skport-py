"""Owner activity uses token-bound snapshots and the shared resource normalizer."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from skport import ClientConfig, ImageSource, Language, Role, TargetNotFound
from skport.games.endfield.client import EndfieldClient
from skport.games.endfield.models import LiveStatus


@pytest.fixture
def owner_client() -> EndfieldClient:
    raw = SimpleNamespace(
        role_for=AsyncMock(return_value=Role("owner-role", "2")),
        owned_card=AsyncMock(
            return_value={
                "detail": {
                    "base": {"name": "Owner"},
                    "currentTs": 1_700_000_000,
                    "dungeon": {"curStamina": 300, "maxStamina": 240, "maxTs": 1_700_000_300},
                    "credit": {"count": 12, "total": 40, "nextRefreshTs": 1_700_003_600},
                }
            }
        ),
        detail=AsyncMock(side_effect=AssertionError("owner activity cannot fetch a public snapshot")),
    )
    api = SimpleNamespace(
        config=ClientConfig(lang=Language.JA, icon_source=ImageSource.ENKA),
        endfield=raw,
        pool=SimpleNamespace(credential_for=AsyncMock(return_value=SimpleNamespace(user_id="owner-social"))),
        resolve_target=AsyncMock(side_effect=AssertionError("owner activity cannot resolve a public target")),
    )
    return EndfieldClient(api)


@pytest.mark.parametrize("language", [None, Language.KO])
async def test_owner_activity_preserves_identity_source_clock_and_overflow(
    owner_client: EndfieldClient, language: Language | None
) -> None:
    report = await owner_client.owned_activity(token="owner-token", role="3_owner-role_2", lang=language)

    assert isinstance(report, LiveStatus)
    assert (report.player.skport_id, report.player.game_uid, report.player.server_id, report.player.name) == (
        "owner-social", "owner-role", "2", "Owner"
    )
    assert report.server_time == datetime.fromtimestamp(1_700_000_000, UTC)
    assert report.sanity.current == 300 and report.sanity.maximum == 240
    assert report.sanity.ratio == 1.25
    assert report.sanity.recovery_at == datetime.fromtimestamp(1_700_000_300, UTC)
    assert report.credits.refresh_at == datetime.fromtimestamp(1_700_003_600, UTC)
    assert report.preferred_image_source == ImageSource.ENKA
    assert report.daily is None and report.weekly is None
    owner_client.raw.role_for.assert_awaited_once_with("owner-token", role="3_owner-role_2", lang=language)
    owner_client.raw.owned_card.assert_awaited_once_with(
        token="owner-token", role=Role("owner-role", "2"), lang=language
    )
    owner_client.api.pool.credential_for.assert_awaited_once_with("owner-token")
    owner_client.raw.detail.assert_not_awaited()
    owner_client.api.resolve_target.assert_not_awaited()
    assert owner_client._assets is None and owner_client._build_service is None


async def test_owner_activity_rejects_a_role_outside_the_token_bindings(owner_client: EndfieldClient) -> None:
    owner_client.raw.role_for.side_effect = TargetNotFound("role does not belong to the token")
    with pytest.raises(TargetNotFound):
        await owner_client.owned_activity(token="owner-token", role=Role("other-role", "2"))
    owner_client.raw.owned_card.assert_not_awaited()
    owner_client.api.pool.credential_for.assert_not_awaited()


async def test_owner_activity_requires_an_explicit_token(owner_client: EndfieldClient) -> None:
    with pytest.raises(TypeError):
        await owner_client.owned_activity()
    owner_client.raw.role_for.assert_not_awaited()
