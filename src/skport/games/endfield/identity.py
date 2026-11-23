"""Endfield role identities and unambiguous public target selection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from skport.errors import ConfigError, DecodeError, TargetNotFound


@dataclass(frozen=True, slots=True)
class Role:
    """An Endfield role within one account's binding list."""

    role_id: str
    server_id: str
    nickname: str = ""
    level: int = 0
    is_default: bool = False
    is_banned: bool = False
    server_type: str = ""
    server_name: str = ""
    account_uid: str = ""
    is_default_binding: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "role_id", _identifier(self.role_id, "role_id"))
        object.__setattr__(self, "server_id", _identifier(self.server_id, "server_id"))

    @property
    def game_role(self) -> str:
        """Return the owner-role header used by Endfield endpoints."""
        return f"3_{self.role_id}_{self.server_id}"


@dataclass(frozen=True, slots=True)
class Target:
    """A public SKPORT user, game role UID, and server combination."""

    user_id: str
    role_id: str
    server_id: str

    def __post_init__(self) -> None:
        for field_name in ("user_id", "role_id", "server_id"):
            object.__setattr__(self, field_name, _identifier(getattr(self, field_name), field_name))

    def query(self) -> dict[str, str]:
        """Return the target parameters required by public card endpoints."""
        return {"roleId": self.role_id, "serverId": self.server_id, "userId": self.user_id}


def _identifier(value: Any, field_name: str) -> str:
    """Normalize a required identity without accepting missing or boolean values."""
    if value is None or isinstance(value, bool) or not str(value).strip():
        raise ConfigError(f"{field_name} must be a nonempty identifier")
    return str(value).strip()


def parse_roles(data: Mapping[str, Any]) -> tuple[Role, ...]:
    """Extract roles without conflating account and per-account role defaults."""
    if not isinstance(data, Mapping):
        raise DecodeError("game binding data must be an object")
    result: dict[tuple[str, str, str], Role] = {}
    for app in data.get("list") or []:
        if not isinstance(app, Mapping):
            raise DecodeError("game binding app entries must be objects")
        if app.get("appCode") != "endfield":
            continue
        for binding in app.get("bindingList") or []:
            if not isinstance(binding, Mapping):
                raise DecodeError("game binding entries must be objects")
            if binding.get("isDelete"):
                continue
            default = binding.get("defaultRole") or {}
            if not isinstance(default, Mapping):
                raise DecodeError("default game role must be an object")
            default_uid = app.get("defaultUid")
            default_binding: bool | None
            if default_uid is not None and str(default_uid).strip():
                default_binding = str(binding.get("uid")) == str(default_uid)
            else:
                default_binding = bool(binding["isDefault"]) if "isDefault" in binding else None
            for item in binding.get("roles") or []:
                if not isinstance(item, Mapping):
                    raise DecodeError("game role entries must be objects")
                if not item.get("roleId") or item.get("serverId") is None:
                    continue
                role = Role(
                    role_id=item["roleId"],
                    server_id=item["serverId"],
                    nickname=str(item.get("nickname") or ""),
                    level=int(item.get("level") or 0),
                    is_default=(
                        str(default.get("roleId")) == str(item["roleId"])
                        and str(default.get("serverId")) == str(item["serverId"])
                    )
                    if default.get("roleId") is not None and default.get("serverId") is not None
                    else bool(item.get("isDefault")),
                    is_banned=bool(item.get("isBanned")),
                    server_type=str(item.get("serverType") or ""),
                    server_name=str(item.get("serverName") or ""),
                    account_uid=str(binding.get("uid") or ""),
                    is_default_binding=default_binding,
                )
                result[(role.role_id, role.server_id, role.account_uid)] = role
    return tuple(result.values())


def select_role(
    roles: tuple[Role, ...],
    *,
    role_id: str | int | None = None,
    server_id: str | int | None = None,
) -> Role:
    """Select explicit roles across accounts, or the default account's role."""
    candidates = [
        role
        for role in roles
        if (role_id is None or role.role_id == str(role_id))
        and (server_id is None or role.server_id == str(server_id))
    ]
    if not candidates:
        raise TargetNotFound("no visible Endfield role matches the supplied identifiers")
    if len(candidates) == 1:
        return candidates[0]
    if role_id is None and server_id is None:
        preferred = [role for role in candidates if role.is_default_binding is True]
        if len(preferred) == 1:
            return preferred[0]
        if len({role.account_uid for role in preferred}) > 1:
            raise TargetNotFound("multiple default Endfield accounts; provide both role_id and server_id")
        if not preferred and all(role.is_default_binding is None for role in candidates):
            preferred = candidates
        defaults = [role for role in preferred if role.is_default]
        if len(defaults) == 1:
            return defaults[0]
    raise TargetNotFound("multiple Endfield roles match; provide both role_id and server_id")
