"""Public and owner Endfield clients with normalized card-ready outputs."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from skport.api import SkportAPI
from skport.assets import AssetManager
from skport.config import ClientConfig, Language, parse_language
from skport.errors import ConfigError, DecodeError
from skport.games.base import Game
from skport.games.endfield.clean.user import build_verified_user
from skport.games.endfield.identity import Role, Target, parse_roles, select_role
from skport.games.endfield.models import (
    CharacterBuild,
    ContractState,
    FactoryState,
    LiveStatus,
    MonumentState,
    PlayerCard,
    PlayerIdentity,
    VerifiedUser,
)
from skport.games.endfield.selection import character_records, select_character

if TYPE_CHECKING:
    from skport.games.endfield.builds import BuildService


class EndfieldClient:
    """Separate public showcase reads from explicit token-owner operations.

    Domain methods return Pydantic output by default. raw=True preserves the
    phase-one dictionary/list behavior; raw endpoint methods remain on raw.
    """

    game: Game | str = Game.ENDFIELD

    def __init__(
        self,
        api: SkportAPI,
        *,
        assets: AssetManager | None = None,
        config: ClientConfig | None = None,
    ) -> None:
        self.api = api
        self.raw = api.endfield
        self.config = config or api.config
        self._assets = assets
        self._owns_assets = assets is None
        self._build_service: Any = None

    @property
    def assets(self) -> AssetManager:
        """Share canonical assets without fetching during client construction."""
        if self._assets is None:
            self._assets = AssetManager(self.config, self.api.transport)
        return self._assets

    @property
    def builds(self) -> BuildService:
        """Lazily create the shared public/owner normalization service."""
        from skport.games.endfield.builds import BuildService

        if self._build_service is None:
            self._build_service = BuildService(self.api, self.assets, self.config)
        return self._build_service

    async def __aenter__(self) -> EndfieldClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Close only canonical resources created by this game client."""
        if self._owns_assets and self._assets is not None:
            await self._assets.close()

    async def resolve(
        self,
        skport_id: str | int,
        *,
        role_id: str | int | None = None,
        server_id: str | int | None = None,
        lang: str | Language | None = None,
    ) -> Target:
        """Discover the game UID and validate optional role/server constraints."""
        return await self.api.resolve_target(skport_id, role_id=role_id, server_id=server_id, lang=lang)

    async def profile(self, *, skport_id: str | int, lang: str | Language | None = None) -> dict[str, Any]:
        """Fetch raw public SKPORT social metadata independent of game builds."""
        return await self.api.user(skport_id=skport_id, lang=lang)

    async def verify_skid(
        self,
        skport_id: str | int,
        *,
        role_id: str | int | None = None,
        server_id: str | int | None = None,
        lang: str | Language | None = None,
    ) -> VerifiedUser:
        """Verify a public SKPORT profile and return its selected Endfield identity."""
        if not isinstance(skport_id, (str, int)) or isinstance(skport_id, bool) or not str(skport_id).strip():
            raise ConfigError("skport_id must be a nonempty identifier")
        normalized_id = str(skport_id).strip()
        language = self._language(lang)
        bindings, social = await asyncio.gather(
            self.api.binding(skport_id=normalized_id, lang=language, ttl=0),
            self.api.user(skport_id=normalized_id, lang=language, ttl=0),
        )
        selected = select_role(parse_roles(bindings), role_id=role_id, server_id=server_id)
        return build_verified_user(social, selected, "public", expected_id=normalized_id)

    async def verify_token(
        self,
        token: str,
        *,
        role: Role | str | None = None,
        lang: str | Language | None = None,
    ) -> VerifiedUser:
        """Verify the explicit token owner and return their social/game information."""
        if not isinstance(token, str) or not token.strip():
            raise ConfigError("account tokens must be nonempty strings")
        language = self._language(lang)
        selected, social = await asyncio.gather(
            self.raw.role_for(token, role=role, lang=language, ttl=0),
            self.api.user(token=token, lang=language, ttl=0),
        )
        return build_verified_user(social, selected, "owner")

    async def card(
        self,
        *,
        skport_id: str | int,
        role_id: str | int | None = None,
        server_id: str | int | None = None,
        lang: str | Language | None = None,
        raw: bool = False,
    ) -> PlayerCard | dict[str, Any]:
        """Fetch a public player snapshot with canonical builds and statistics."""
        target = await self.resolve(skport_id, role_id=role_id, server_id=server_id, lang=lang)
        data = await self.raw.detail(target, lang=lang)
        return data if raw else await self.builds.card(data, target, self._language(lang))

    async def characters(
        self,
        *,
        skport_id: str | int,
        role_id: str | int | None = None,
        server_id: str | int | None = None,
        showcase_only: bool = False,
        full: bool = False,
        lang: str | Language | None = None,
        raw: bool = False,
    ) -> list[CharacterBuild] | list[dict[str, Any]]:
        """Return exposed characters, optionally in configured showcase order."""
        target = await self.resolve(skport_id, role_id=role_id, server_id=server_id, lang=lang)
        data = await self.raw.detail(target, lang=lang)
        records = character_records(data, showcase_only)
        if full:
            responses = await asyncio.gather(
                *(self.raw.character(target, char_id=str(item["id"]), lang=lang) for item in records)
            )
            records = [_character_detail(response) for response in responses]
        if raw:
            return records
        return await self.builds.characters(records, self._player(target, data), self._language(lang))

    async def character(
        self,
        *,
        skport_id: str | int,
        char_id: str | None = None,
        name: str | None = None,
        index: int | None = None,
        role_id: str | int | None = None,
        server_id: str | int | None = None,
        showcase_only: bool = False,
        full: bool = True,
        lang: str | Language | None = None,
        raw: bool = False,
    ) -> CharacterBuild | dict[str, Any]:
        """Select one public character by opaque ID, localized name, or index."""
        if sum(value is not None for value in (char_id, name, index)) != 1:
            raise ConfigError("Supply exactly one of char_id=, name=, or index=")
        if char_id is not None and not char_id:
            raise ConfigError("char_id cannot be empty")
        target = await self.resolve(skport_id, role_id=role_id, server_id=server_id, lang=lang)
        card_data = None
        if char_id is None or not full:
            card_data = await self.raw.detail(target, lang=lang)
            selected = select_character(
                character_records(card_data, showcase_only),
                char_id=char_id,
                name=name,
                index=index,
            )
            if not full:
                record = selected
            else:
                record = _character_detail(
                    await self.raw.character(target, char_id=str(selected["id"]), lang=lang)
                )
        else:
            record = _character_detail(await self.raw.character(target, char_id=char_id, lang=lang))
        if raw:
            return record
        return (
            await self.builds.characters([record], self._player(target, card_data), self._language(lang))
        )[0]

    async def owned_card(
        self,
        *,
        token: str,
        role: Role | str | None = None,
        lang: str | Language | None = None,
        raw: bool = False,
    ) -> PlayerCard | dict[str, Any]:
        """Fetch the explicitly authenticated owner's game snapshot."""
        selected = await self.raw.role_for(token, role=role, lang=lang)
        data = await self.raw.owned_card(token=token, role=selected, lang=lang)
        if raw:
            return data
        target = await self._owner_target(token, selected)
        return await self.builds.card(data, target, self._language(lang), scope="owner")

    async def owned_characters(
        self,
        *,
        token: str,
        role: Role | str | None = None,
        full: bool = False,
        lang: str | Language | None = None,
        raw: bool = False,
    ) -> list[CharacterBuild] | list[dict[str, Any]]:
        """Read the token owner's returned roster, rather than a public showcase."""
        selected = await self.raw.role_for(token, role=role, lang=lang)
        data = await self.raw.owned_card(token=token, role=selected, lang=lang)
        records = character_records(data, False)
        if full:
            responses = await asyncio.gather(
                *(
                    self.raw.owned_character(token=token, role=selected, char_id=str(item["id"]), lang=lang)
                    for item in records
                )
            )
            records = [_character_detail(response) for response in responses]
        if raw:
            return records
        target = await self._owner_target(token, selected)
        return await self.builds.characters(records, self._player(target, data), self._language(lang))

    async def owned_character(
        self,
        *,
        token: str,
        char_id: str | None = None,
        name: str | None = None,
        index: int | None = None,
        operator_id: str | None = None,
        role: Role | str | None = None,
        full: bool = True,
        lang: str | Language | None = None,
        raw: bool = False,
    ) -> CharacterBuild | dict[str, Any]:
        """Select one owner build by opaque ID, localized name, or roster index."""
        if sum(value is not None for value in (char_id, name, index)) != 1:
            raise ConfigError("Supply exactly one of char_id=, name=, or index=")
        if char_id is not None and not char_id:
            raise ConfigError("char_id cannot be empty")
        if operator_id is not None and not operator_id:
            raise ConfigError("operator_id cannot be empty")
        selected = await self.raw.role_for(token, role=role, lang=lang)
        card_data = None
        if char_id is None or not full:
            card_data = await self.raw.owned_card(token=token, role=selected, lang=lang)
            record = select_character(
                character_records(card_data, False), char_id=char_id, name=name, index=index
            )
            char_id = str(record["id"])
        if full:
            record = _character_detail(
                await self.raw.owned_character(
                    token=token,
                    char_id=char_id,
                    operator_id=operator_id,
                    role=selected,
                    lang=lang,
                )
            )
        if raw:
            return record
        target = await self._owner_target(token, selected)
        return (
            await self.builds.characters([record], self._player(target, card_data), self._language(lang))
        )[0]

    async def activity(self, **ids: Any) -> LiveStatus:
        """Normalize resource and activity state from the public player snapshot."""
        from skport.games.endfield.clean.progress import build_live_status

        data, target = await self._snapshot_data(ids)
        return build_live_status(data, self._player(target, data), self.config.icon_source)

    async def factory(self, **ids: Any) -> FactoryState:
        """Normalize regions, settlements and spaceship crew for factory cards."""
        from skport.games.endfield.clean.world import build_factory_state

        data, target = await self._snapshot_data(ids)
        return build_factory_state(data, self._player(target, data), self.config.icon_source)

    async def monument(self, **ids: Any) -> MonumentState:
        """Normalize stage, completion, medal and team information."""
        from skport.games.endfield.clean.endgame import build_monument_report

        data, target = await self._snapshot_data(ids)
        detail = await self.raw.indie_hard(target, lang=ids.get("lang"))
        roster = await self.builds.characters(
            character_records(data, False),
            self._player(target, data),
            self._language(ids.get("lang")),
        )
        return build_monument_report(
            detail, self._player(target, data), self.config.icon_source, roster=roster
        )

    async def contract(self, **ids: Any) -> ContractState:
        """Normalize crisis-contract summaries and detailed runs."""
        from skport.games.endfield.clean.endgame import build_contract_report

        data, target = await self._snapshot_data(ids)
        detail = await self.raw.crisis_contract(target, lang=ids.get("lang"))
        roster = await self.builds.characters(
            character_records(data, False),
            self._player(target, data),
            self._language(ids.get("lang")),
        )
        return build_contract_report(
            detail, self._player(target, data), self.config.icon_source, roster=roster
        )

    async def attendance(
        self,
        *,
        token: str,
        role: Role | str | None = None,
        lang: str | Language | None = None,
    ) -> dict[str, Any]:
        """Read attendance using the explicitly supplied account's token."""
        return await self.raw.attendance(token=token, role=role, lang=lang)

    async def check_in(
        self,
        *,
        token: str,
        role: Role | str | None = None,
        lang: str | Language | None = None,
    ) -> dict[str, Any]:
        """Claim daily attendance for the explicitly supplied account."""
        return await self.raw.check_in(token=token, role=role, lang=lang)

    async def inventory(
        self,
        *,
        token: str,
        role: Role | str | None = None,
        lang: str | Language | None = None,
    ) -> dict[str, Any]:
        """Read inventory using the explicitly supplied account's token."""
        return await self.raw.inventory(token=token, role=role, lang=lang)

    async def _owner_target(self, token: str, role: Role) -> Target:
        credential = await self.api.pool.credential_for(token)
        return Target(credential.user_id, role.role_id, role.server_id)

    async def _snapshot_data(self, ids: dict[str, Any]) -> tuple[dict[str, Any], Target]:
        target = await self.resolve(
            ids["skport_id"],
            role_id=ids.get("role_id"),
            server_id=ids.get("server_id"),
            lang=ids.get("lang"),
        )
        return await self.raw.detail(target, lang=ids.get("lang")), target

    def _language(self, value: str | Language | None) -> str:
        return parse_language(value or self.config.lang).value

    @staticmethod
    def _player(target: Target, data: dict[str, Any] | None = None) -> PlayerIdentity:
        base = ((data or {}).get("detail") or {}).get("base") or {}
        return PlayerIdentity(
            skport_id=target.user_id,
            game_uid=target.role_id,
            server_id=target.server_id,
            name=str(base.get("name") or ""),
        )


def _character_detail(response: dict[str, Any]) -> dict[str, Any]:
    """Require a real build response instead of silently returning a summary."""
    detail = response.get("detail")
    if not isinstance(detail, dict):
        raise DecodeError("The character endpoint did not return a detail object")
    return detail
