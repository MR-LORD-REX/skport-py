"""Owner character endpoints preserve the requested account and role."""

from __future__ import annotations

import pytest
from test_multi_account_bindings import BindingAPI, two_accounts, wire_binding, wire_profile, wire_role

from skport import Language, Role, TargetNotFound


@pytest.mark.parametrize("language", tuple(Language))
async def test_owned_card_selects_secondary_owner_account(language: Language) -> None:
    api = BindingAPI(
        wire_profile(wire_binding("public", wire_role("public-role", "2"))),
        two_accounts(),
    )
    result = await api.endfield.owned_card(
        token="owner-token", role=Role("role-secondary", "3"), lang=language
    )
    assert result is api.output
    binding = api.calls[0][2]
    assert binding["token"] == "owner-token" and binding["params"] is None
    method, path, request = api.calls[-1]
    assert method == "GET" and path.endswith("/card/detail")
    assert request["params"] == {"roleId": "role-secondary", "serverId": "3"}
    assert request["token"] == "owner-token"
    assert request["role"] == "3_role-secondary_3"
    assert request["lang"] == language


async def test_owned_character_keeps_owner_and_operator_identity() -> None:
    api = BindingAPI(wire_profile(), two_accounts())
    result = await api.endfield.owned_character(
        token="owner-token",
        char_id="character-hash",
        operator_id="operator-hash",
        role="3_role-secondary_3",
    )
    assert result is api.output
    _, path, request = api.calls[-1]
    assert path.endswith("/card/char")
    assert request["params"] == {
        "roleId": "role-secondary",
        "serverId": "3",
        "operatorId": "operator-hash",
        "charId": "character-hash",
    }
    assert request["token"] == "owner-token"
    assert request["role"] == "3_role-secondary_3"


@pytest.mark.parametrize("method", ["owned_card", "owned_character"])
async def test_owned_build_methods_require_token_and_reject_foreign_roles(method: str) -> None:
    api = BindingAPI(two_accounts(), wire_profile(wire_binding("viewer", wire_role("viewer-role", "2"))))
    call = getattr(api.endfield, method)
    kwargs = {"char_id": "character"} if method == "owned_character" else {}
    with pytest.raises(TypeError):
        await call(**kwargs)
    with pytest.raises(TargetNotFound):
        await call(token="owner-token", role=Role("role-secondary", "3"), **kwargs)
    assert len(api.calls) == 1
    assert api.calls[0][1].endswith("/binding")
    assert api.calls[0][2]["token"] == "owner-token"
