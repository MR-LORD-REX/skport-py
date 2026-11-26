"""Endpoint contracts for identity, localization, and account isolation."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import pytest

from skport.api import SkportAPI
from skport.config import ClientConfig, Language
from skport.errors import AuthError, ConfigError, DecodeError, TargetNotFound
from skport.games.endfield.identity import Role, Target, parse_roles, select_role

LANGUAGES = tuple(Language)
TARGET = Target("public-user", "4000000001", "2")
OWNER = Role("4000000001", "2", is_default=True, account_uid="G-owner")


def binding(*roles: Role) -> dict[str, Any]:
    return {
        "list": [
            {
                "appCode": "endfield",
                "bindingList": [
                    {
                        "uid": role.account_uid,
                        "roles": [
                            {"roleId": role.role_id, "serverId": role.server_id, "isDefault": role.is_default}
                        ],
                    }
                    for role in roles
                ],
            }
        ]
    }


class RecordingPool:
    def __init__(self) -> None:
        self.locks: dict[str, asyncio.Lock] = {}
        self.active: dict[str, int] = {}
        self.max_active: dict[str, int] = {}

    @asynccontextmanager
    async def lease(self, *, token: str):
        lock = self.locks.setdefault(token, asyncio.Lock())
        async with lock:
            self.active[token] = self.active.get(token, 0) + 1
            self.max_active[token] = max(self.max_active.get(token, 0), self.active[token])
            try:
                yield object()
            finally:
                self.active[token] -= 1


class RecordingAPI(SkportAPI):
    def __init__(self) -> None:
        self.config = ClientConfig()
        self.pool = RecordingPool()
        self._credential_cache: dict[tuple[str, str, str], tuple[float, str]] = {}
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.output: Any = {"records": [1, 2], "futureField": {"nested": True}}
        self.bindings = binding(OWNER)
        self.external_outputs: list[Any] = []

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
        if path.endswith("/binding"):
            return self.bindings
        return self.output

    async def external_request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.calls.append((method, url, kwargs))
        await asyncio.sleep(0)
        result = self.external_outputs.pop(0) if self.external_outputs else self.output
        if isinstance(result, BaseException):
            raise result
        return result


@pytest.mark.parametrize("name", ["cards", "binding", "user", "web_user"])
async def test_shared_lookup_requires_one_identity(name: str) -> None:
    api = RecordingAPI()
    method = getattr(api, name)
    with pytest.raises(ConfigError):
        await method()
    with pytest.raises(ConfigError):
        await method(skport_id=TARGET.user_id, token="owner")
    assert not api.calls
    await method(token="owner")
    assert api.calls[-1][2]["token"] == "owner"
    assert api.calls[-1][2]["params"] is None


@pytest.mark.parametrize("language", LANGUAGES)
async def test_public_endpoints_preserve_data_and_locale(language: Language) -> None:
    api = RecordingAPI()
    raw = api.endfield
    calls = [
        lambda: api.cards(skport_id=TARGET.user_id, lang=language),
        lambda: api.user(skport_id=TARGET.user_id, lang=language),
        lambda: api.web_user(skport_id=TARGET.user_id, lang=language),
        lambda: api.user_items(TARGET.user_id, lang=language),
        lambda: raw.detail(TARGET, lang=language),
        lambda: raw.character(TARGET, char_id="opaque", lang=language),
        lambda: raw.crisis_contract(TARGET, contract_id="contract", lang=language),
        lambda: raw.indie_hard(TARGET, lang=language),
        lambda: raw.enums(lang=language),
        lambda: raw.wiki_catalog(type_sub_id=1, lang=language),
        lambda: raw.wiki_item(1, lang=language),
        lambda: raw.char_banners(lang=language),
        lambda: raw.weapon_banners(lang=language),
    ]
    for call in calls:
        assert await call() is api.output
        kwargs = api.calls[-1][2]
        assert kwargs["lang"] == language
        assert not kwargs.get("role")
        assert not kwargs.get("token")
    character = next(kwargs for _, path, kwargs in api.calls if path.endswith("/card/char"))
    assert character["params"] == {**TARGET.query(), "operatorId": "opaque", "charId": "opaque"}


def test_role_selection_honors_filters_and_rejects_ambiguity() -> None:
    second = Role("4000000002", "3")
    roles = parse_roles(binding(OWNER, second))
    assert select_role(roles).role_id == OWNER.role_id
    assert select_role(roles, server_id="3").role_id == second.role_id
    with pytest.raises(TargetNotFound):
        select_role(roles, role_id="does-not-exist")
    with pytest.raises(TargetNotFound, match="multiple"):
        select_role((Role("1", "2"), Role("2", "2")), server_id="2")


@pytest.mark.parametrize(
    "role_id,server_id",
    [(None, None), (TARGET.role_id, None), (None, TARGET.server_id), (4000000001, 2)],
)
@pytest.mark.parametrize("language", [Language.EN, Language.JA])
async def test_resolve_target_discovers_and_validates_binding(
    role_id: str | int | None,
    server_id: str | int | None,
    language: Language,
) -> None:
    api = RecordingAPI()
    target = await api.resolve_target(
        TARGET.user_id,
        role_id=role_id,
        server_id=server_id,
        lang=language,
    )
    assert target == TARGET
    assert len(api.calls) == 1
    method, path, kwargs = api.calls[0]
    assert method == "GET" and path.endswith("/binding")
    assert kwargs["params"] == {"uid": TARGET.user_id}
    assert kwargs["lang"] == language


@pytest.mark.parametrize(
    "role_id,server_id",
    [("different", None), ("different", TARGET.server_id), (TARGET.role_id, "3"), (None, "3")],
)
async def test_resolve_target_rejects_mismatch_before_any_target_request(
    role_id: str | None,
    server_id: str | None,
) -> None:
    api = RecordingAPI()
    with pytest.raises(TargetNotFound):
        await api.resolve_target(TARGET.user_id, role_id=role_id, server_id=server_id)
    assert len(api.calls) == 1
    assert api.calls[0][1].endswith("/binding")


async def test_resolve_target_uses_default_or_explicit_matching_role() -> None:
    api = RecordingAPI()
    second = Role("4000000002", "3", account_uid="G-second")
    api.bindings = binding(second, OWNER)
    assert await api.resolve_target(TARGET.user_id) == TARGET
    assert await api.resolve_target(TARGET.user_id, role_id=second.role_id) == Target(
        TARGET.user_id,
        second.role_id,
        second.server_id,
    )


async def test_resolve_target_requires_server_when_game_uid_is_ambiguous() -> None:
    api = RecordingAPI()
    other_server = Role(OWNER.role_id, "3", account_uid="G-second")
    api.bindings = binding(OWNER, other_server)
    with pytest.raises(TargetNotFound, match="multiple"):
        await api.resolve_target(TARGET.user_id, role_id=OWNER.role_id)
    assert await api.resolve_target(
        TARGET.user_id,
        role_id=OWNER.role_id,
        server_id=other_server.server_id,
    ) == Target(TARGET.user_id, OWNER.role_id, other_server.server_id)


@pytest.mark.parametrize("data", [{"list": []}, binding()])
async def test_resolve_target_rejects_profiles_without_endfield_roles(data: dict[str, Any]) -> None:
    api = RecordingAPI()
    api.bindings = data
    with pytest.raises(TargetNotFound):
        await api.resolve_target(TARGET.user_id)


@pytest.mark.parametrize("method", ["attendance", "check_in", "inventory"])
async def test_owner_action_requires_token_and_validates_role(method: str) -> None:
    api = RecordingAPI()
    call = getattr(api.endfield, method)
    with pytest.raises(TypeError):
        await call()
    with pytest.raises(TargetNotFound):
        await call(token="owner", role=Role("other-user-role", "2"))
    assert all(path.endswith("/binding") for _, path, _ in api.calls)
    result = await call(token="owner", role=OWNER)
    assert result is api.output
    kwargs = api.calls[-1][2]
    assert kwargs["token"] == "owner"
    assert kwargs["role"] == OWNER.game_role
    if method == "check_in":
        assert api.calls[-1][0] == "POST"
        assert kwargs["cache"] is False
        assert kwargs["payload"] == {}


async def test_account_calls_are_serialized_for_the_explicit_token() -> None:
    api = RecordingAPI()
    await asyncio.gather(api.account_basic(token="owner"), api.third_party(token="owner"))
    assert api.pool.max_active == {"owner": 1}
    assert all(kwargs["params"] == {"token": "owner"} for _, _, kwargs in api.calls)


@pytest.mark.parametrize(
    "language,service",
    [
        (Language.EN, "en-us"),
        (Language.JA, "ja-jp"),
        (Language.KO, "ko-kr"),
        (Language.ZH_HANT, "zh-tw"),
        (Language.ZH_HANS, "zh-cn"),
    ],
)
async def test_news_uses_service_locale(language: Language, service: str) -> None:
    api = RecordingAPI()
    assert await api.endfield.news(lang=language) is api.output
    assert api.calls[-1][2]["params"]["lang"] == service


async def test_pull_credentials_reuse_account_uid_and_do_not_mutate_pages() -> None:
    api = RecordingAPI()
    page = {"list": [{"seqId": "9", "gachaTs": "1790000000000"}], "hasMore": False}
    api.external_outputs = [{"token": "grant-access"}, binding(OWNER), {"token": "record-access"}, page, page]
    assert await api.endfield.character_pulls(token="owner", lang="ja") is page
    assert await api.endfield.character_pulls(token="owner", lang="ja") is page
    grants = [kwargs for _, path, kwargs in api.calls if path.endswith("/grant")]
    exchanges = [kwargs for _, path, kwargs in api.calls if path.endswith("/u8_token_by_uid")]
    assert len(grants) == 1
    assert grants[0]["payload"]["type"] == 1
    assert exchanges[0]["payload"]["uid"] == "G-owner"
    assert api.pool.max_active == {"owner": 1}
    assert api.calls[-1][2]["params"]["lang"] == "ja-jp"


async def test_pull_pagination_rejects_repeated_cursor() -> None:
    api = RecordingAPI()
    page = {"list": [{"seqId": "9"}], "hasMore": True}
    api.external_outputs = [{"token": "grant"}, binding(OWNER), {"token": "record"}, page, page]
    with pytest.raises(DecodeError, match="repeated"):
        async for _ in api.endfield.pulls.iter_character_pages(token="owner"):
            pass


async def test_pull_account_binding_rejects_a_different_owner_role() -> None:
    api = RecordingAPI()
    api.external_outputs = [{"token": "grant"}, binding(Role("different", "2", account_uid="G-other"))]
    with pytest.raises(TargetNotFound):
        await api.endfield.weapon_pools(token="owner")
    assert not any(path.endswith("/u8_token_by_uid") for _, path, _ in api.calls)


async def test_pull_record_cache_is_scoped_to_each_explicit_account() -> None:
    api = RecordingAPI()
    api.external_outputs = [
        {"token": "grant-a"},
        binding(OWNER),
        {"token": "record-a"},
        {"list": ["a"]},
        {"token": "grant-b"},
        binding(OWNER),
        {"token": "record-b"},
        {"list": ["b"]},
    ]
    assert await api.endfield.weapon_pools(token="account-a") == {"list": ["a"]}
    assert await api.endfield.weapon_pools(token="account-b") == {"list": ["b"]}
    requests = [kwargs for _, path, kwargs in api.calls if path.endswith("/weapon/pool")]
    assert [request["params"]["token"] for request in requests] == ["record-a", "record-b"]


async def test_expired_pull_record_token_is_replaced_once_for_same_owner() -> None:
    api = RecordingAPI()
    page = {"list": []}
    api.external_outputs = [
        {"token": "grant-1"},
        binding(OWNER),
        {"token": "old-record"},
        AuthError("expired"),
        {"token": "grant-2"},
        binding(OWNER),
        {"token": "new-record"},
        page,
    ]
    assert await api.endfield.weapon_pools(token="owner") is page
    assert len([path for _, path, _ in api.calls if path.endswith("/grant")]) == 2
    assert api.pool.max_active == {"owner": 1}
