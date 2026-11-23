"""Raw Endfield endpoints with explicit public and owner identities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from skport.config import Language, parse_language, service_language
from skport.errors import ConfigError
from skport.games.endfield import endpoints as ep
from skport.games.endfield.identity import Role, Target, parse_roles, select_role
from skport.games.endfield.pulls import PullHistoryAPI

if TYPE_CHECKING:
    from skport.api.raw import SkportAPI


class EndfieldRawAPI:
    """Return decoded endpoint data without building models or calculating stats."""

    def __init__(self, api: SkportAPI) -> None:
        self.api = api
        self.pulls = PullHistoryAPI(self)

    async def detail(
        self,
        target: Target,
        *,
        lang: str | Language | None = None,
        ttl: float | None = None,
    ) -> Any:
        """Fetch a public Endfield card for the supplied target."""
        return await self.api.request("GET", ep.DETAIL, params=target.query(), lang=lang, ttl=ttl)

    async def character(
        self,
        target: Target,
        *,
        char_id: str,
        operator_id: str | None = None,
        lang: str | Language | None = None,
        ttl: float | None = None,
    ) -> Any:
        """Fetch a character by its opaque SKPORT character ID."""
        if not char_id:
            raise ConfigError("char_id must not be empty")
        params = {**target.query(), "operatorId": operator_id or char_id, "charId": char_id}
        return await self.api.request("GET", ep.CHARACTER, params=params, lang=lang, ttl=ttl)

    async def crisis_contract(
        self,
        target: Target,
        *,
        contract_id: str | None = None,
        lang: str | Language | None = None,
        ttl: float | None = None,
    ) -> Any:
        """Fetch public crisis-contract records, optionally for a specific contract."""
        params = target.query()
        if contract_id is not None:
            params["contractId"] = contract_id
        return await self.api.request("GET", ep.CONTRACT, params=params, lang=lang, ttl=ttl)

    async def indie_hard(
        self,
        target: Target,
        *,
        lang: str | Language | None = None,
        ttl: float | None = None,
    ) -> Any:
        """Fetch a target's public independent-hard dungeon records."""
        return await self.api.request("GET", ep.MONUMENT, params=target.query(), lang=lang, ttl=ttl)

    async def enums(self, *, lang: str | Language | None = None, ttl: float | None = None) -> Any:
        """Fetch localized Endfield enum labels."""
        return await self.api.request("GET", ep.ENUMS, lang=lang, ttl=ttl)

    async def wiki_catalog(
        self,
        *,
        type_sub_id: int,
        type_main_id: int = 1,
        lang: str | Language | None = None,
        ttl: float | None = None,
    ) -> Any:
        """Fetch the requested localized wiki catalog section."""
        return await self.api.request(
            "GET",
            ep.WIKI_CATALOG,
            params={"typeMainId": type_main_id, "typeSubId": type_sub_id},
            lang=lang,
            ttl=ttl,
        )

    async def wiki_item(
        self,
        item_id: str | int,
        *,
        lang: str | Language | None = None,
        ttl: float | None = None,
    ) -> Any:
        """Fetch one localized SKPORT wiki entry."""
        return await self.api.request("GET", ep.WIKI_INFO, params={"id": str(item_id)}, lang=lang, ttl=ttl)

    async def char_banners(self, *, lang: str | Language | None = None, ttl: float | None = None) -> Any:
        """Fetch current character banner metadata."""
        return await self.api.request("GET", ep.CHAR_BANNERS, lang=lang, ttl=ttl)

    async def weapon_banners(self, *, lang: str | Language | None = None, ttl: float | None = None) -> Any:
        """Fetch current weapon banner metadata."""
        return await self.api.request("GET", ep.WEAPON_BANNERS, lang=lang, ttl=ttl)

    async def role_for(
        self,
        token: str,
        *,
        role: Role | str | None = None,
        lang: str | Language | None = None,
    ) -> Role:
        """Resolve an owner's Endfield role and validate any supplied role header."""
        data = await self.api.binding(token=token, lang=lang)
        roles = parse_roles(data)
        if role is None:
            return select_role(roles)
        if isinstance(role, Role):
            return select_role(roles, role_id=role.role_id, server_id=role.server_id)
        parts = role.split("_")
        if len(parts) != 3 or parts[0] != "3":
            raise ConfigError("role must be an Endfield Role or a '3_<roleId>_<serverId>' header")
        return select_role(roles, role_id=parts[1], server_id=parts[2])

    async def attendance(
        self,
        *,
        token: str,
        role: Role | str | None = None,
        lang: str | Language | None = None,
        ttl: float | None = None,
    ) -> Any:
        """Fetch attendance only for a role owned by the supplied account token."""
        owner = await self.role_for(token, role=role, lang=lang)
        return await self.api.request(
            "GET",
            ep.ATTENDANCE,
            token=token,
            role=owner.game_role,
            lang=lang,
            ttl=ttl,
        )

    async def check_in(
        self,
        *,
        token: str,
        role: Role | str | None = None,
        lang: str | Language | None = None,
    ) -> Any:
        """Claim a daily reward once for the explicitly selected owner's role."""
        owner = await self.role_for(token, role=role, lang=lang)
        return await self.api.request(
            "POST",
            ep.ATTENDANCE,
            payload={},
            token=token,
            role=owner.game_role,
            lang=lang,
            cache=False,
        )

    async def inventory(
        self,
        *,
        token: str,
        role: Role | str | None = None,
        lang: str | Language | None = None,
        ttl: float | None = None,
    ) -> Any:
        """Fetch raw inventory for a role verified against the owner's binding."""
        owner = await self.role_for(token, role=role, lang=lang)
        return await self.api.request(
            "GET",
            ep.INVENTORY,
            params={"roleId": owner.role_id, "serverId": owner.server_id},
            token=token,
            role=owner.game_role,
            lang=lang,
            ttl=ttl,
        )

    async def news(self, *, lang: str | Language | None = None) -> Any:
        """Fetch official game bulletin records using the service's language code."""
        language = parse_language(lang or self.api.config.lang)
        return await self.api.external_request(
            "GET",
            self.api.config.hosts.news + ep.NEWS,
            params={
                "lang": service_language(language),
                "platform": "Windows",
                "channel": 6,
                "type": 0,
                "code": self.api.config.protocol.bulletin_code,
                "hideDetail": 0,
                "server": 3,
            },
            lang=language,
        )

    async def character_pulls(
        self,
        *,
        token: str,
        pool_type: str = "E_CharacterGachaPoolType_Special",
        seq_id: str = "",
        role: Role | str | None = None,
        lang: str | Language | None = None,
    ) -> Any:
        """Fetch one raw character pull page; an explicit account token is required."""
        return await self.pulls.character_pulls(
            token=token,
            pool_type=pool_type,
            seq_id=seq_id,
            role=role,
            lang=lang,
        )

    async def weapon_pools(
        self,
        *,
        token: str,
        role: Role | str | None = None,
        lang: str | Language | None = None,
    ) -> Any:
        """Fetch raw weapon pull pools for the explicitly selected account."""
        return await self.pulls.weapon_pools(token=token, role=role, lang=lang)

    async def weapon_pulls(
        self,
        *,
        token: str,
        pool_id: str,
        seq_id: str = "",
        role: Role | str | None = None,
        lang: str | Language | None = None,
    ) -> Any:
        """Fetch one raw weapon pull page; an explicit account token is required."""
        return await self.pulls.weapon_pulls(
            token=token, pool_id=pool_id, seq_id=seq_id, role=role, lang=lang
        )

    async def user_items(
        self,
        user_id: str | int,
        *,
        view_kind: int = 2,
        page_token: str = "",
        page_size: int = 20,
        lang: str | Language | None = None,
        ttl: float | None = None,
    ) -> Any:
        """Fetch a public community feed through the shared SKPORT endpoint group."""
        return await self.api.user_items(
            user_id,
            view_kind=view_kind,
            page_token=page_token,
            page_size=page_size,
            lang=lang,
            ttl=ttl,
        )
