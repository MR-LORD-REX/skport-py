"""Raw account, community, and game access over one request pipeline."""

from __future__ import annotations

from typing import Any

from skport.api import endpoints as ep
from skport.api.base import RequestAPI
from skport.config import Language, parse_language
from skport.errors import ConfigError
from skport.games.endfield.api import EndfieldRawAPI
from skport.games.endfield.endpoints import OWNER_PATHS
from skport.games.endfield.identity import Target, parse_roles, select_role


class SkportAPI(RequestAPI):
    """Provide unmodified endpoint data using pooled account authentication.

    Public lookups require a target SKPORT ID. Owner lookups require an explicit
    account token, so omitting a target never picks an arbitrary pool account.
    """

    owner_paths = OWNER_PATHS

    @property
    def endfield(self) -> EndfieldRawAPI:
        """Return the Endfield endpoint group sharing this API's resources."""
        group = getattr(self, "_endfield", None)
        if group is None or group.api is not self:
            group = self._endfield = EndfieldRawAPI(self)
        return group

    async def cards(
        self,
        *,
        skport_id: str | int | None = None,
        token: str | None = None,
        lang: str | Language | None = None,
        ttl: float | None = None,
    ) -> Any:
        """Fetch public game cards, or the explicitly selected owner's cards."""
        params = _lookup(skport_id, token, "uid")
        return await self.request("GET", ep.CARDS, params=params, token=token, lang=lang, ttl=ttl)

    async def binding(
        self,
        *,
        skport_id: str | int | None = None,
        token: str | None = None,
        lang: str | Language | None = None,
        ttl: float | None = None,
    ) -> Any:
        """Fetch a target's visible game bindings or an explicit owner's bindings."""
        params = _lookup(skport_id, token, "uid")
        return await self.request("GET", ep.BINDING, params=params, token=token, lang=lang, ttl=ttl)

    async def user(
        self,
        *,
        skport_id: str | int | None = None,
        token: str | None = None,
        lang: str | Language | None = None,
        ttl: float | None = None,
    ) -> Any:
        """Fetch SKPORT social profile data using the public API route."""
        params = _lookup(skport_id, token, "id")
        return await self.request("GET", ep.PROFILE, params=params, token=token, lang=lang, ttl=ttl)

    async def web_user(
        self,
        *,
        skport_id: str | int | None = None,
        token: str | None = None,
        lang: str | Language | None = None,
        ttl: float | None = None,
    ) -> Any:
        """Fetch SKPORT social profile data using the web route."""
        params = _lookup(skport_id, token, "id")
        return await self.request("GET", ep.WEB_PROFILE, params=params, token=token, lang=lang, ttl=ttl)

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
        """Fetch a public user's community item feed without changing its records."""
        if page_size < 1:
            raise ConfigError("page_size must be positive")
        target = _lookup(user_id, None, "userId")
        return await self.request(
            "GET",
            ep.USER_ITEMS,
            params={**(target or {}), "viewKind": view_kind, "pageToken": page_token, "pageSize": page_size},
            lang=lang,
            ttl=ttl,
        )

    async def account_basic(self, *, token: str, lang: str | Language | None = None) -> Any:
        """Fetch Gryphline account details for the supplied account token."""
        return await self._account_info(ep.ACCOUNT_BASIC, token, lang)

    async def third_party(self, *, token: str, lang: str | Language | None = None) -> Any:
        """Fetch third-party account links for the supplied account token."""
        return await self._account_info(ep.THIRD_PARTY, token, lang)

    async def _account_info(self, path: str, token: str, lang: str | Language | None) -> Any:
        """Serialize publisher-account reads with other requests using this token."""
        language = parse_language(lang or self.config.lang)
        async with self.pool.lease(token=token):
            return await self.external_request(
                "GET",
                self.config.hosts.account + path,
                params={"token": token},
                headers={"x-language": language.value},
                lang=language,
            )

    async def resolve_target(
        self,
        skport_id: str | int,
        *,
        role_id: str | int | None = None,
        server_id: str | int | None = None,
        lang: str | Language | None = None,
    ) -> Target:
        """Discover a public user's Endfield UID or validate the supplied UID.

        Bindings are checked even when both role_id and server_id are provided.
        A mismatched UID/server raises TargetNotFound before fetching game data.
        """
        data = await self.binding(skport_id=skport_id, lang=lang)
        role = select_role(parse_roles(data), role_id=role_id, server_id=server_id)
        return Target(str(skport_id), role.role_id, role.server_id)


def _lookup(skport_id: str | int | None, token: str | None, parameter: str) -> dict[str, str] | None:
    """Require one identity mode before deciding whether to include a target query."""
    if skport_id is None and not token:
        raise ConfigError("provide skport_id for a public lookup or token for an owner lookup")
    if skport_id is not None and token is not None:
        raise ConfigError("provide either skport_id or token for this lookup")
    if skport_id is None:
        return None
    if isinstance(skport_id, bool) or not str(skport_id).strip():
        raise ConfigError("skport_id must be a nonempty identifier")
    return {parameter: str(skport_id).strip()}


AccountRawAPI = SkportAPI
