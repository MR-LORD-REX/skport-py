"""Account-bound pull-history credentials and raw page access."""

from __future__ import annotations

import hashlib
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from skport.api.endpoints import GRANT
from skport.config import Language, parse_language, service_language
from skport.errors import AuthError, ConfigError, DecodeError, TargetNotFound
from skport.games.endfield import endpoints as ep
from skport.games.endfield.identity import Role

if TYPE_CHECKING:
    from skport.games.endfield.api import EndfieldRawAPI


class PullHistoryAPI:
    """Keep record credentials in RAM and serialize all account-bound requests."""

    def __init__(self, endfield: EndfieldRawAPI) -> None:
        self.endfield = endfield
        self.api = endfield.api
        self._tokens: dict[tuple[str, str, str], tuple[float, str]] = self.api._credential_cache

    async def _record_token(self, token: str, owner: Role, language: Language) -> str:
        """Reuse a record token or exchange an account grant for the owner's game token."""
        key = self._key(token, owner)
        cached = self._tokens.get(key)
        if cached is not None and cached[0] > time.monotonic():
            return cached[1]
        grant = await self.api.external_request(
            "POST",
            self.api.config.hosts.account + GRANT,
            payload={"token": token, "appCode": self.api.config.protocol.gacha_app_code, "type": 1},
            headers={"x-language": language.value},
            lang=language,
        )
        if not isinstance(grant, dict) or not grant.get("token"):
            raise DecodeError("pull-history grant did not contain an account access token")
        access_token = grant["token"]
        bindings = await self.api.external_request(
            "GET",
            self.api.config.hosts.binding + ep.PULL_BINDING,
            params={"token": access_token, "appCode": "endfield"},
            lang=language,
        )
        if not isinstance(bindings, dict):
            raise DecodeError("pull-history binding response must be an object")
        matching = {
            str(binding["uid"])
            for app in bindings.get("list") or []
            if app.get("appCode") == "endfield"
            for binding in app.get("bindingList") or []
            if binding.get("uid")
            and any(
                str(item.get("roleId")) == owner.role_id and str(item.get("serverId")) == owner.server_id
                for item in binding.get("roles") or []
            )
        }
        if len(matching) != 1:
            raise TargetNotFound("the selected owner role has no unique pull-history account binding")
        result = await self.api.external_request(
            "POST",
            self.api.config.hosts.binding + ep.PULL_TOKEN,
            payload={"uid": matching.pop(), "token": access_token},
            lang=language,
        )
        if not isinstance(result, dict) or not result.get("token"):
            raise DecodeError("pull-history binding did not contain a game record token")
        record_token = str(result["token"])
        self._tokens[key] = (time.monotonic() + 600, record_token)
        return record_token

    async def _page(
        self,
        path: str,
        *,
        token: str,
        role: Role | str | None,
        lang: str | Language | None,
        parameters: dict[str, str],
    ) -> Any:
        """Read one page within an owner lease, renewing rejected record tokens once."""
        language = parse_language(lang or self.api.config.lang)
        owner = await self.endfield.role_for(token, role=role, lang=language)
        async with self.api.pool.lease(token=token):
            for attempt in range(2):
                record_token = await self._record_token(token, owner, language)
                try:
                    return await self.api.external_request(
                        "GET",
                        self.api.config.hosts.webview + path,
                        params={
                            "lang": service_language(language),
                            "token": record_token,
                            "server_id": owner.server_id,
                            **parameters,
                        },
                        lang=language,
                    )
                except AuthError:
                    self._tokens.pop(self._key(token, owner), None)
                    if attempt:
                        raise

    @staticmethod
    def _key(token: str, owner: Role) -> tuple[str, str, str]:
        """Keep credential caches separate for each account, role, and server."""
        return (hashlib.sha256(token.encode()).hexdigest(), owner.role_id, owner.server_id)

    def clear(self) -> None:
        """Drop retained pull-history tokens when the owning API closes."""
        self._tokens.clear()

    async def character_pulls(
        self,
        *,
        token: str,
        pool_type: str = "E_CharacterGachaPoolType_Special",
        seq_id: str = "",
        role: Role | str | None = None,
        lang: str | Language | None = None,
    ) -> Any:
        """Fetch one character record page for the supplied owner's banner."""
        parameters = {"pool_type": pool_type}
        if seq_id:
            parameters["seq_id"] = seq_id
        return await self._page(ep.CHAR_PULLS, token=token, role=role, lang=lang, parameters=parameters)

    async def weapon_pools(
        self,
        *,
        token: str,
        role: Role | str | None = None,
        lang: str | Language | None = None,
    ) -> Any:
        """Fetch the owner's raw weapon pool list."""
        return await self._page(ep.WEAPON_POOLS, token=token, role=role, lang=lang, parameters={})

    async def weapon_pulls(
        self,
        *,
        token: str,
        pool_id: str,
        seq_id: str = "",
        role: Role | str | None = None,
        lang: str | Language | None = None,
    ) -> Any:
        """Fetch one weapon record page for the supplied owner's pool."""
        if not pool_id:
            raise ConfigError("pool_id must not be empty")
        parameters = {"pool_id": pool_id}
        if seq_id:
            parameters["seq_id"] = seq_id
        return await self._page(ep.WEAPON_PULLS, token=token, role=role, lang=lang, parameters=parameters)

    async def iter_character_pages(self, *, token: str, **kwargs: Any) -> AsyncIterator[Any]:
        """Yield raw pages and reject a repeated or absent continuation cursor."""
        cursor = ""
        seen: set[str] = set()
        while True:
            page = await self.character_pulls(token=token, seq_id=cursor, **kwargs)
            yield page
            if not page.get("hasMore"):
                return
            rows = page.get("list") or []
            next_cursor = str(rows[-1].get("seqId") or "") if rows else ""
            if not next_cursor or next_cursor in seen:
                raise DecodeError("pull-history continuation cursor is missing or repeated")
            seen.add(next_cursor)
            cursor = next_cursor
