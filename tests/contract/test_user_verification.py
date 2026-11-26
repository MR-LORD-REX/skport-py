"""Verification separates social/game identities and authenticates only its scope."""

from __future__ import annotations

import copy
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio

from skport import (
    AuthError,
    ClientConfig,
    ConfigError,
    DecodeError,
    Language,
    Role,
    SkportAPI,
    TargetNotFound,
)
from skport.api import endpoints as ep
from skport.auth import Credential, TokenPool
from skport.games.endfield.client import EndfieldClient
from skport.games.endfield.models import VerifiedUser

PUBLIC_ID = "1700000000001"
OWNER_ID = "1800000000001"
OWNER_TOKEN = "test-owner-token"
VIEWER_TOKEN = "test-viewer-token"


def social(user_id: str, username: str) -> dict[str, Any]:
    return {"user": {"basicUser": {"id": user_id, "nickname": username, "avatar": "https://example.test/a.png"}}}


def bindings(scope: str) -> dict[str, Any]:
    """Place a secondary default role before the account actually selected."""
    accounts = []
    for kind, server, selected in (("secondary", "3", False), ("primary", "2", True)):
        role = {
            "roleId": f"{scope}-{kind}-role",
            "serverId": server,
            "nickname": f"{scope.title()} {kind.title()} Endmin",
            "serverName": "Asia" if server == "2" else "America",
            "isDefault": True,
        }
        accounts.append(
            {
                "uid": f"publisher-{scope}-{kind}",
                "nickName": "Publisher alias, not the in-game name",
                "isDefault": selected,
                "roles": [role],
                "defaultRole": dict(role),
            }
        )
    return {
        "list": [{"appCode": "endfield", "defaultUid": f"publisher-{scope}-primary", "bindingList": accounts}],
        "serverDefaultBinding": {},
    }


class NoExternalTransport:
    async def request(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("verification must not contact assets or external services")


class VerificationFlow:
    def __init__(self) -> None:
        self.failed: set[str] = set()

    async def authenticate(self, token: str) -> Credential:
        if token in self.failed:
            raise AuthError("test authentication rejected")
        return Credential(token, f"credential-{token}", f"signing-key-{token}")


class VerificationAPI(SkportAPI):
    """Keep the real raw helpers and token pool, replacing only endpoint I/O."""

    def __init__(self) -> None:
        config = ClientConfig(assets_offline=True)
        self.flow = VerificationFlow()
        pool = TokenPool([VIEWER_TOKEN], config, self.flow)
        super().__init__(pool=pool, config=config, transport=NoExternalTransport())
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.authenticated_tokens: list[str] = []
        self.public_bindings = bindings("public")
        self.owner_bindings = bindings("owner")
        self.public_social: Any = social(PUBLIC_ID, "Public SKPort username")
        self.owner_social: Any = social(OWNER_ID, "Owner SKPort username")

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
        if path not in {ep.BINDING, ep.PROFILE}:
            raise AssertionError("verification must only read bindings and social profiles")
        token = kwargs.get("token")
        async with self.pool.lease(token=token) as unit:
            self.authenticated_tokens.append(unit.token)
            if path == ep.BINDING:
                output = self.owner_bindings if token is not None else self.public_bindings
            else:
                output = self.owner_social if token is not None else self.public_social
            return copy.deepcopy(output)


@pytest_asyncio.fixture
async def verification() -> AsyncIterator[tuple[EndfieldClient, VerificationAPI]]:
    api = VerificationAPI()
    client = EndfieldClient(api)
    try:
        yield client, api
    finally:
        await client.close()
        await api.close()
        await api.pool.close()


def assert_lightweight_uncached(client: EndfieldClient, api: VerificationAPI, expected_calls: int = 2) -> None:
    assert len(api.calls) == expected_calls
    assert all(method == "GET" and kwargs["ttl"] == 0 for method, _, kwargs in api.calls)
    assert client._assets is None and client._build_service is None


@pytest.mark.parametrize("keyword", [False, True])
@pytest.mark.parametrize("skport_id", [PUBLIC_ID, int(PUBLIC_ID)])
async def test_public_verification_returns_distinct_social_and_game_names(
    verification: tuple[EndfieldClient, VerificationAPI], keyword: bool, skport_id: str | int
) -> None:
    client, api = verification
    user = await client.verify_skid(skport_id=skport_id) if keyword else await client.verify_skid(skport_id)
    assert isinstance(user, VerifiedUser)
    assert user.model_dump() == {
        "skport_id": PUBLIC_ID,
        "skport_username": "Public SKPort username",
        "game_uid": "public-primary-role",
        "in_game_name": "Public Primary Endmin",
        "server_id": "2",
        "server_name": "Asia",
        "source_scope": "public",
    }
    assert all(kwargs["token"] is None for _, _, kwargs in api.calls)
    assert {path: kwargs["params"] for _, path, kwargs in api.calls} == {
        ep.BINDING: {"uid": PUBLIC_ID}, ep.PROFILE: {"id": PUBLIC_ID}
    }
    assert api.authenticated_tokens == [VIEWER_TOKEN, VIEWER_TOKEN]
    assert_lightweight_uncached(client, api)


@pytest.mark.parametrize("language", tuple(Language))
async def test_public_verification_selects_explicit_nondefault_role_and_language(
    verification: tuple[EndfieldClient, VerificationAPI], language: Language
) -> None:
    client, api = verification
    user = await client.verify_skid(PUBLIC_ID, role_id="public-secondary-role", server_id="3", lang=language)
    assert (user.game_uid, user.in_game_name, user.server_id, user.server_name) == (
        "public-secondary-role", "Public Secondary Endmin", "3", "America"
    )
    assert all(kwargs["lang"] == language for _, _, kwargs in api.calls)
    assert_lightweight_uncached(client, api)


@pytest.mark.parametrize("keyword", [False, True])
async def test_token_verification_does_not_substitute_public_user_or_rotate_owner(
    verification: tuple[EndfieldClient, VerificationAPI], keyword: bool
) -> None:
    client, api = verification
    user = await client.verify_token(token=OWNER_TOKEN) if keyword else await client.verify_token(OWNER_TOKEN)
    assert (user.skport_id, user.skport_username, user.game_uid, user.in_game_name, user.source_scope) == (
        OWNER_ID, "Owner SKPort username", "owner-primary-role", "Owner Primary Endmin", "owner"
    )
    assert api.authenticated_tokens == [OWNER_TOKEN, OWNER_TOKEN]
    assert all(kwargs["token"] == OWNER_TOKEN and kwargs["params"] is None for _, _, kwargs in api.calls)
    assert len(api.pool) == 1 and [unit.token for unit in api.pool.units] == [VIEWER_TOKEN]
    assert_lightweight_uncached(client, api)
    rendered = user.model_dump_json() + repr(user)
    assert all(secret not in rendered for secret in (OWNER_TOKEN, "credential-", "signing-key-"))
    assert set(user.model_dump()) == {
        "skport_id", "skport_username", "game_uid", "in_game_name", "server_id", "server_name", "source_scope"
    }
    public = await client.verify_skid(PUBLIC_ID)
    assert public.skport_id == PUBLIC_ID and public.source_scope == "public"
    assert api.authenticated_tokens[-2:] == [VIEWER_TOKEN, VIEWER_TOKEN]


@pytest.mark.parametrize("role", [Role("owner-secondary-role", "3"), "3_owner-secondary-role_3"])
async def test_token_verification_selects_only_explicit_owned_role(
    verification: tuple[EndfieldClient, VerificationAPI], role: Role | str
) -> None:
    client, api = verification
    user = await client.verify_token(OWNER_TOKEN, role=role, lang="ja")
    assert (user.game_uid, user.in_game_name, user.server_id) == (
        "owner-secondary-role", "Owner Secondary Endmin", "3"
    )
    assert all(kwargs["token"] == OWNER_TOKEN and kwargs["lang"] == "ja" for _, _, kwargs in api.calls)
    assert_lightweight_uncached(client, api)


@pytest.mark.parametrize("scope", ["public", "owner"])
async def test_verification_refreshes_endpoint_reads_on_repeated_calls(
    verification: tuple[EndfieldClient, VerificationAPI], scope: str
) -> None:
    client, api = verification
    verify = client.verify_token if scope == "owner" else client.verify_skid
    identifier = OWNER_TOKEN if scope == "owner" else PUBLIC_ID
    first = await verify(identifier)
    target = api.owner_social if scope == "owner" else api.public_social
    target["user"]["basicUser"]["nickname"] = "Updated username"
    second = await verify(identifier)
    assert first.skport_username != second.skport_username == "Updated username"
    assert_lightweight_uncached(client, api, 4)


@pytest.mark.parametrize("token", ["", "   ", None, 123, True, b"bytes-token"])
async def test_invalid_token_is_rejected_before_io(
    verification: tuple[EndfieldClient, VerificationAPI], token: Any
) -> None:
    client, api = verification
    with pytest.raises(ConfigError):
        await client.verify_token(token)
    assert not api.calls and not api.authenticated_tokens


@pytest.mark.parametrize("skport_id", ["", "   ", None, True])
async def test_invalid_public_identifier_is_rejected_before_io(
    verification: tuple[EndfieldClient, VerificationAPI], skport_id: Any
) -> None:
    client, api = verification
    with pytest.raises(ConfigError):
        await client.verify_skid(skport_id)
    assert not api.calls


@pytest.mark.parametrize("scope", ["public", "owner"])
@pytest.mark.parametrize(
    "response",
    [None, {}, {"user": []}, {"user": {"basicUser": []}}, {"user": {"basicUser": {"nickname": "Name"}}},
     {"user": {"basicUser": {"id": PUBLIC_ID}}}],
)
async def test_malformed_social_profile_does_not_verify(
    verification: tuple[EndfieldClient, VerificationAPI], scope: str, response: Any
) -> None:
    client, api = verification
    if scope == "owner":
        api.owner_social = response
        method, identifier = client.verify_token, OWNER_TOKEN
    else:
        api.public_social = response
        method, identifier = client.verify_skid, PUBLIC_ID
    with pytest.raises(DecodeError):
        await method(identifier)


async def test_public_profile_cannot_return_a_different_skport_id(
    verification: tuple[EndfieldClient, VerificationAPI],
) -> None:
    client, api = verification
    api.public_social = social(OWNER_ID, "Different user")
    with pytest.raises(DecodeError):
        await client.verify_skid(PUBLIC_ID)


@pytest.mark.parametrize("scope", ["public", "owner"])
async def test_account_without_endfield_binding_is_not_an_endfield_user(
    verification: tuple[EndfieldClient, VerificationAPI], scope: str
) -> None:
    client, api = verification
    if scope == "owner":
        api.owner_bindings = {"list": []}
        method, identifier = client.verify_token, OWNER_TOKEN
    else:
        api.public_bindings = {"list": []}
        method, identifier = client.verify_skid, PUBLIC_ID
    with pytest.raises(TargetNotFound):
        await method(identifier)


@pytest.mark.parametrize("scope", ["public", "owner"])
async def test_ambiguous_default_requires_explicit_role_selection(
    verification: tuple[EndfieldClient, VerificationAPI], scope: str
) -> None:
    client, api = verification
    response = api.owner_bindings if scope == "owner" else api.public_bindings
    app = response["list"][0]
    app.pop("defaultUid")
    for account in app["bindingList"]:
        account.pop("isDefault")
    method = client.verify_token if scope == "owner" else client.verify_skid
    with pytest.raises(TargetNotFound):
        await method(OWNER_TOKEN if scope == "owner" else PUBLIC_ID)


async def test_public_role_cannot_be_substituted_for_owner_verification(
    verification: tuple[EndfieldClient, VerificationAPI],
) -> None:
    client, api = verification
    with pytest.raises(TargetNotFound):
        await client.verify_token(OWNER_TOKEN, role=Role("public-primary-role", "2"))
    assert all(kwargs["token"] == OWNER_TOKEN for _, _, kwargs in api.calls)


async def test_rejected_token_propagates_authentication_error(
    verification: tuple[EndfieldClient, VerificationAPI],
) -> None:
    client, api = verification
    api.flow.failed.add(OWNER_TOKEN)
    with pytest.raises(AuthError):
        await client.verify_token(OWNER_TOKEN)
    assert not api.authenticated_tokens
    assert all(kwargs["token"] == OWNER_TOKEN for _, _, kwargs in api.calls)
