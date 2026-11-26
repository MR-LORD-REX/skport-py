"""Nested account defaults and selection across public and owner bindings."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

from skport import ClientConfig, Role, SkportAPI, Target, TargetNotFound
from skport.games.endfield.identity import parse_roles, select_role


def wire_role(uid: str, server: str, *, default: bool = True) -> dict[str, Any]:
    return {"roleId": uid, "serverId": server, "isDefault": default}


def wire_binding(
    account_uid: str,
    *roles: dict[str, Any],
    selected: bool | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"uid": account_uid, "roles": list(roles)}
    if selected is not None:
        result["isDefault"] = selected
    defaults = [role for role in roles if role.get("isDefault")]
    if len(defaults) == 1:
        result["defaultRole"] = dict(defaults[0])
    return result


def wire_profile(
    *bindings: dict[str, Any],
    default_uid: str | None = None,
) -> dict[str, Any]:
    app: dict[str, Any] = {"appCode": "endfield", "bindingList": list(bindings)}
    if default_uid is not None:
        app["defaultUid"] = default_uid
    return {"list": [app], "serverDefaultBinding": {}}


def two_accounts() -> dict[str, Any]:
    return wire_profile(
        wire_binding("account-secondary", wire_role("role-secondary", "3"), selected=False),
        wire_binding("account-primary", wire_role("role-primary", "2"), selected=True),
        default_uid="account-primary",
    )


def test_conflicting_selected_accounts_are_not_resolved_by_one_local_default() -> None:
    profile = wire_profile(
        wire_binding("first", wire_role("role-a", "2"), selected=True),
        wire_binding("second", wire_role("role-b", "3", default=False), selected=True),
    )
    roles = parse_roles(profile)
    with pytest.raises(TargetNotFound, match="multiple default"):
        select_role(roles)
    assert select_role(roles, role_id="role-b", server_id="3").account_uid == "second"


class RecordingPool:
    @asynccontextmanager
    async def lease(self, *, token: str):
        yield object()


class BindingAPI(SkportAPI):
    def __init__(self, public: dict[str, Any], owner: dict[str, Any]) -> None:
        self.config = ClientConfig()
        self.pool = RecordingPool()
        self.public = public
        self.owner = owner
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.external_outputs: list[Any] = []
        self._credential_cache = {}
        self.output = {"futureField": {"records": [1, 2]}}

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
        if path.endswith("/binding"):
            return self.owner if kwargs.get("token") is not None else self.public
        return self.output

    async def external_request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.calls.append((method, url, kwargs))
        return self.external_outputs.pop(0)


def test_local_role_defaults_do_not_override_selected_account() -> None:
    roles = parse_roles(two_accounts())
    assert all(role.is_default for role in roles)
    assert {role.role_id: role.is_default_binding for role in roles} == {
        "role-primary": True,
        "role-secondary": False,
    }
    selected = select_role(roles)
    assert (selected.role_id, selected.server_id, selected.account_uid) == (
        "role-primary",
        "2",
        "account-primary",
    )


def test_app_default_uid_takes_precedence_over_binding_flags() -> None:
    data = wire_profile(
        wire_binding("account-secondary", wire_role("role-secondary", "3"), selected=True),
        wire_binding("account-primary", wire_role("role-primary", "2"), selected=False),
        default_uid="account-primary",
    )
    roles = parse_roles(data)
    assert select_role(roles).account_uid == "account-primary"
    assert {role.account_uid: role.is_default_binding for role in roles} == {
        "account-primary": True,
        "account-secondary": False,
    }


def test_binding_default_flag_is_used_when_app_selection_is_absent() -> None:
    data = wire_profile(
        wire_binding("secondary", wire_role("second", "3"), selected=False),
        wire_binding("primary", wire_role("first", "2"), selected=True),
    )
    assert select_role(parse_roles(data)).role_id == "first"


def test_default_role_pair_takes_precedence_over_role_flags() -> None:
    primary = wire_binding(
        "primary",
        wire_role("flag-default", "2"),
        wire_role("pair-default", "3", default=False),
        selected=True,
    )
    primary["defaultRole"] = wire_role("pair-default", "3", default=False)
    roles = parse_roles(wire_profile(primary, default_uid="primary"))
    assert {role.role_id: role.is_default for role in roles} == {
        "flag-default": False,
        "pair-default": True,
    }
    assert select_role(roles).role_id == "pair-default"


def test_missing_selection_metadata_preserves_legacy_unique_role_default() -> None:
    roles = parse_roles(
        wire_profile(
            wire_binding("first", wire_role("first-role", "2", default=False)),
            wire_binding("second", wire_role("second-role", "3")),
        )
    )
    assert all(role.is_default_binding is None for role in roles)
    assert select_role(roles).role_id == "second-role"


def test_selected_binding_default_role_is_used_with_multiple_servers() -> None:
    data = wire_profile(
        wire_binding(
            "primary",
            wire_role("other-server", "3", default=False),
            wire_role("preferred-server", "2"),
            selected=True,
        ),
        wire_binding("secondary", wire_role("secondary-role", "2"), selected=False),
        default_uid="primary",
    )
    roles = parse_roles(data)
    assert select_role(roles).role_id == "preferred-server"
    assert select_role(roles, role_id="other-server", server_id="3").role_id == "other-server"


@pytest.mark.parametrize(
    "role_id,server_id",
    [
        ("role-secondary", None),
        (None, "3"),
        ("role-secondary", "3"),
    ],
)
def test_explicit_filters_can_select_non_default_account(role_id, server_id) -> None:
    selected = select_role(parse_roles(two_accounts()), role_id=role_id, server_id=server_id)
    assert (selected.role_id, selected.server_id, selected.account_uid) == (
        "role-secondary",
        "3",
        "account-secondary",
    )


def test_filtered_ambiguity_does_not_fall_back_to_global_default() -> None:
    data = wire_profile(
        wire_binding("primary", wire_role("shared-uid", "2"), selected=True),
        wire_binding("secondary", wire_role("shared-uid", "3"), selected=False),
        default_uid="primary",
    )
    roles = parse_roles(data)
    with pytest.raises(TargetNotFound, match="multiple"):
        select_role(roles, role_id="shared-uid")
    assert select_role(roles, role_id="shared-uid", server_id="3").account_uid == "secondary"


def test_conflicting_selected_bindings_remain_ambiguous() -> None:
    roles = parse_roles(
        wire_profile(
            wire_binding("first", wire_role("first-role", "2"), selected=True),
            wire_binding("second", wire_role("second-role", "3"), selected=True),
        )
    )
    with pytest.raises(TargetNotFound, match="multiple"):
        select_role(roles)


async def test_public_secondary_account_uses_targets_binding_not_owners() -> None:
    api = BindingAPI(two_accounts(), wire_profile(wire_binding("viewer", wire_role("viewer-role", "2"))))
    target = await api.resolve_target("other-skport-user", role_id="role-secondary", server_id="3")
    assert target == Target("other-skport-user", "role-secondary", "3")
    kwargs = api.calls[0][2]
    assert kwargs["params"] == {"uid": "other-skport-user"}
    assert kwargs["token"] is None
    assert (await api.endfield.detail(target)) is api.output
    assert api.calls[-1][2]["params"] == target.query()
    assert "role" not in api.calls[-1][2]


async def test_owner_secondary_account_preserves_token_role_and_account_uid() -> None:
    api = BindingAPI(wire_profile(), two_accounts())
    selected = await api.endfield.role_for("owner-token", role=Role("role-secondary", "3"))
    assert selected.account_uid == "account-secondary"
    assert selected.is_default_binding is False
    result = await api.endfield.inventory(token="owner-token", role=selected)
    assert result is api.output
    binding_calls = [kwargs for _, path, kwargs in api.calls if path.endswith("/binding")]
    assert all(call["params"] is None and call["token"] == "owner-token" for call in binding_calls)
    kwargs = api.calls[-1][2]
    assert kwargs["token"] == "owner-token"
    assert kwargs["role"] == "3_role-secondary_3"
    assert kwargs["params"] == {"roleId": "role-secondary", "serverId": "3"}


async def test_public_role_cannot_be_substituted_for_an_owner_role() -> None:
    api = BindingAPI(two_accounts(), wire_profile(wire_binding("viewer", wire_role("viewer-role", "2"))))
    with pytest.raises(TargetNotFound):
        await api.endfield.inventory(token="owner-token", role=Role("role-secondary", "3"))
    assert len(api.calls) == 1
    assert api.calls[0][1].endswith("/binding")
    assert api.calls[0][2]["params"] is None
    assert not api.external_outputs


async def test_secondary_pull_account_uses_its_own_binding_uid() -> None:
    api = BindingAPI(wire_profile(), two_accounts())
    page = {"list": [{"seqId": "10"}], "hasMore": False}
    api.external_outputs = [
        {"token": "grant-token"},
        two_accounts(),
        {"token": "record-token"},
        page,
    ]
    assert await api.endfield.character_pulls(token="owner-token", role=Role("role-secondary", "3")) is page
    exchange = next(kwargs for _, url, kwargs in api.calls if url.endswith("/u8_token_by_uid"))
    assert exchange["payload"]["uid"] == "account-secondary"
    records = api.calls[-1][2]["params"]
    assert records["server_id"] == "3"
    assert records["token"] == "record-token"
