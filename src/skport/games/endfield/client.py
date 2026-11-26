"""Public and owner Endfield clients with normalized card-ready outputs."""

from __future__ import annotations

import asyncio
from collections.abc import Collection, Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, overload

from skport.api import SkportAPI
from skport.assets import AssetManager
from skport.config import ClientConfig, Language, parse_language
from skport.errors import ConfigError, DecodeError, SkportError, WikiNotFound
from skport.games.base import Game
from skport.games.endfield.clean.attendance import attendance_status, check_in_result
from skport.games.endfield.clean.inventory import enrich_inventory, inventory_wiki_ids
from skport.games.endfield.clean.inventory import inventory as build_inventory
from skport.games.endfield.clean.reference import enum_catalog, notices
from skport.games.endfield.clean.user import build_social_profile, build_verified_user
from skport.games.endfield.identity import Role, Target, parse_roles, select_role
from skport.games.endfield.models import (
    Banner,
    CharacterBuild,
    ContractState,
    FactoryState,
    LiveStatus,
    MonumentState,
    PlayerCard,
    PlayerIdentity,
    PullHistory,
    SocialProfile,
    VerifiedUser,
)
from skport.games.endfield.models.attendance import AttendanceStatus, CheckInResult
from skport.games.endfield.models.base import ModelIssue
from skport.games.endfield.models.inventory import Inventory
from skport.games.endfield.models.reference import EnumCatalog, Notice
from skport.games.endfield.models.wiki import WikiMaterial, WikiPage, WikiSummary
from skport.games.endfield.models.wiki_catalog import WikiBatchResult, WikiCatalogTree, WikiIndex
from skport.games.endfield.selection import character_records, select_character

if TYPE_CHECKING:
    from skport.games.endfield.builds import BuildService
    from skport.games.endfield.models.wiki_operator import WikiOperatorReference
    from skport.games.endfield.models.wiki_upgrade import WikiUpgradeGuide

_WIKI_TTL = 3600
_BANNER_TTL = 600
_WIKI_BATCH_SIZE = 30


def _optional_lookup_issue(path: str, exc: SkportError) -> ModelIssue:
    return ModelIssue(
        code="metadata_lookup_failed",
        message=f"Optional metadata lookup failed ({type(exc).__name__})",
        path=path,
    )


class EndfieldClient:
    """Fetch Endfield player, owner, and wiki data through a shared SKPORT API.

    Public game reads select a player by SKPORT ID. Owner reads require the
    account token and verify the selected role against that token's bindings.
    Access decoded service payloads through ``raw`` or through the ``raw`` option
    on methods that expose it.
    """

    game: Game | str = Game.ENDFIELD

    def __init__(
        self,
        api: SkportAPI,
        *,
        assets: AssetManager | None = None,
        config: ClientConfig | None = None,
    ) -> None:
        """Create an Endfield client over an existing SKPORT API.

        Args:
            api: Shared API for authentication and requests.
            assets: Optional shared canonical asset manager. The caller manages
                its lifetime. The client creates its own manager when needed.
            config: Client settings. Defaults to the API's configuration.
        """
        self.api = api
        self.raw = api.endfield
        self.config = config or api.config
        self._assets = assets
        self._owns_assets = assets is None
        self._build_service: Any = None

    @property
    def assets(self) -> AssetManager:
        """Return the canonical asset manager, creating it on first access."""
        if self._assets is None:
            self._assets = AssetManager(self.config, self.api.transport)
        return self._assets

    @property
    def builds(self) -> BuildService:
        """Return the build service for normalizing cards and character stats."""
        from skport.games.endfield.builds import BuildService

        if self._build_service is None:
            self._build_service = BuildService(self.api, self.assets, self.config)
        return self._build_service

    async def __aenter__(self) -> EndfieldClient:
        """Return this client for an ``async with`` block."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Release the client's owned assets when its context ends."""
        await self.close()

    async def close(self) -> None:
        """Release the canonical asset manager created by this client, if any."""
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
        """Resolve a public SKPORT ID to a visible Endfield role.

        Args:
            skport_id: Public SKPORT community ID of the player.
            role_id: Endfield role ID to match when supplied.
            server_id: Endfield server ID to match when supplied.
            lang: Response language. Defaults to the configured language.

        Returns:
            ``Target`` with the SKPORT ID, Endfield role ID, and server ID.

        Raises:
            TargetNotFound: The filters select no visible role or are ambiguous.
        """
        return await self.api.resolve_target(skport_id, role_id=role_id, server_id=server_id, lang=lang)

    @overload
    async def skport_profile(
        self, skport_id: str | int, *, lang: str | Language | None = None, raw: Literal[False] = False,
    ) -> SocialProfile: ...

    @overload
    async def skport_profile(
        self, skport_id: str | int, *, lang: str | Language | None = None, raw: Literal[True],
    ) -> dict[str, Any]: ...

    @overload
    async def skport_profile(
        self, skport_id: str | int, *, lang: str | Language | None = None, raw: bool,
    ) -> SocialProfile | dict[str, Any]: ...

    async def skport_profile(
        self,
        skport_id: str | int,
        *,
        lang: str | Language | None = None,
        raw: bool = False,
    ) -> SocialProfile | dict[str, Any]:
        """Fetch a public SKPORT community profile.

        Args:
            skport_id: Public SKPORT community ID of the user.
            lang: Response language. Defaults to the configured language.
            raw: Return the decoded community-profile payload.

        Returns:
            ``SocialProfile`` with the community username, biography, avatar,
            and available social counts, or the decoded payload when ``raw=True``.
            Use ``profile()`` to fetch the player's Endfield game data.

        Raises:
            DecodeError: The typed response is malformed or identifies a
                different user from the requested SKPORT ID.
        """
        data = await self.api.user(skport_id=skport_id, lang=lang)
        if raw:
            return data
        return build_social_profile(data, self.config.icon_source, expected_id=str(skport_id).strip())

    async def verify_skid(
        self,
        skport_id: str | int,
        *,
        role_id: str | int | None = None,
        server_id: str | int | None = None,
        lang: str | Language | None = None,
    ) -> VerifiedUser:
        """Verify a public community profile and its visible Endfield binding.

        Args:
            skport_id: Public SKPORT community ID as a string or integer.
            role_id: Endfield role ID to match when supplied.
            server_id: Endfield server ID to match when supplied.
            lang: Response language. Defaults to the configured language.

        Returns:
            ``VerifiedUser`` with social identity and the selected Endfield role,
            built from fresh profile and binding responses.

        Raises:
            ConfigError: The SKPORT ID is empty or has an unsupported type.
            TargetNotFound: The filters select no visible role or are ambiguous.
        """
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
        """Verify an account token and its selected Endfield role.

        Args:
            token: SKPORT account token belonging to the owner.
            role: Optional owner ``Role`` or ``3_<roleId>_<serverId>`` header.
            lang: Response language. Defaults to the configured language.

        Returns:
            ``VerifiedUser`` with social identity and the verified Endfield role,
            built from fresh profile and binding responses.

        Raises:
            ConfigError: The token is empty or the role selector is malformed.
            TargetNotFound: The selector matches no owned role or is ambiguous.
        """
        if not isinstance(token, str) or not token.strip():
            raise ConfigError("account tokens must be nonempty strings")
        language = self._language(lang)
        selected, social = await asyncio.gather(
            self.raw.role_for(token, role=role, lang=language, ttl=0),
            self.api.user(token=token, lang=language, ttl=0),
        )
        return build_verified_user(social, selected, "owner")

    @overload
    async def profile(
        self, skport_id: str | int, *, role_id: str | int | None = None,
        server_id: str | int | None = None, lang: str | Language | None = None,
        raw: Literal[False] = False,
    ) -> PlayerCard: ...

    @overload
    async def profile(
        self, skport_id: str | int, *, role_id: str | int | None = None,
        server_id: str | int | None = None, lang: str | Language | None = None,
        raw: Literal[True],
    ) -> dict[str, Any]: ...

    @overload
    async def profile(
        self, skport_id: str | int, *, role_id: str | int | None = None,
        server_id: str | int | None = None, lang: str | Language | None = None,
        raw: bool,
    ) -> PlayerCard | dict[str, Any]: ...

    async def profile(
        self,
        skport_id: str | int,
        *,
        role_id: str | int | None = None,
        server_id: str | int | None = None,
        lang: str | Language | None = None,
        raw: bool = False,
    ) -> PlayerCard | dict[str, Any]:
        """Fetch the player's public Endfield game profile through containing all the public data .

        Args:
            skport_id: Public SKPORT community ID of the player.
            role_id: Endfield role ID to match when supplied.
            server_id: Endfield server ID to match when supplied.
            lang: Response and model language. Defaults to the configured language.
            raw: Return decoded game-card data and skip build normalization.

        Returns:
            ``PlayerCard`` with exposed player information, operator builds,
            and game progress, or the decoded game-card payload when ``raw=True``.
            Use ``skport_profile()`` for the user's SKPORT community profile.
        """
        return await self.card(skport_id, role_id=role_id, server_id=server_id, lang=lang, raw=raw)

    async def card(
        self,
        skport_id: str | int,
        *,
        role_id: str | int | None = None,
        server_id: str | int | None = None,
        lang: str | Language | None = None,
        raw: bool = False,
    ) -> PlayerCard | dict[str, Any]:
        """Fetch the player's public Endfield game card.

        Args:
            skport_id: Public SKPORT community ID of the player.
            role_id: Endfield role ID to match when supplied.
            server_id: Endfield server ID to match when supplied.
            lang: Response and model language. Defaults to the configured language.
            raw: Return decoded service data and skip build normalization.

        Returns:
            ``PlayerCard`` with the exposed player information, operator builds,
            and game progress, or the decoded card payload when ``raw=True``.
        """
        target = await self.resolve(skport_id, role_id=role_id, server_id=server_id, lang=lang)
        data = await self.raw.detail(target, lang=lang)
        return data if raw else await self.builds.card(data, target, self._language(lang))

    async def characters(
        self,
        skport_id: str | int,
        *,
        role_id: str | int | None = None,
        server_id: str | int | None = None,
        showcase_only: bool = False,
        full: bool = False,
        lang: str | Language | None = None,
        raw: bool = False,
    ) -> list[CharacterBuild] | list[dict[str, Any]]:
        """Fetch the operators exposed by a public Endfield game card.

        Args:
            skport_id: Public SKPORT community ID of the player.
            role_id: Endfield role ID to match when supplied.
            server_id: Endfield server ID to match when supplied.
            showcase_only: Limit the result to the player's configured showcase
                and use its order.
            full: Fetch the individual detail endpoint for every selected operator.
            lang: Response and model language. Defaults to the configured language.
            raw: Return decoded character records and skip build normalization.

        Returns:
            A list of ``CharacterBuild`` models, or the selected service records
            when ``raw=True``.
        """
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
        skport_id: str | int,
        *,
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
        """Fetch one operator from a public Endfield game card.

        Args:
            skport_id: Public SKPORT community ID of the player.
            char_id: Opaque operator ID returned by SKPORT.
            name: Localized operator name. Must match one returned operator.
            index: Zero-based index into the selected roster.
            role_id: Endfield role ID to match when supplied.
            server_id: Endfield server ID to match when supplied.
            showcase_only: Use the configured showcase for roster-based selection.
            full: Fetch the individual operator detail. Set False to use the
                snapshot record.
            lang: Response and model language. Defaults to the configured language.
            raw: Return the selected service record and skip build normalization.

        Returns:
            A ``CharacterBuild``, or the selected decoded record when ``raw=True``.

        Raises:
            ConfigError: Exactly one of ``char_id``, ``name``, or ``index`` is
                required. Ambiguous names and invalid selectors also raise this.
            TargetNotFound: No public target or operator matches the selection.
        """
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
        if card_data is None:
            card_data = await self.raw.detail(target, lang=lang)
        return (
            await self.builds.characters([record], self._player(target, card_data), self._language(lang))
        )[0]

    async def owned_card(
        self,
        token: str,
        *,
        role: Role | str | None = None,
        lang: str | Language | None = None,
        raw: bool = False,
    ) -> PlayerCard | dict[str, Any]:
        """Fetch an Endfield game card using its owner's account token.

        Args:
            token: SKPORT account token belonging to the owner.
            role: Optional owner ``Role`` or ``3_<roleId>_<serverId>`` header.
            lang: Response and model language. Defaults to the configured language.
            raw: Return decoded service data and skip build normalization.

        Returns:
            ``PlayerCard`` for the selected role with owner scope, or the decoded
            card payload when ``raw=True``.
        """
        selected = await self.raw.role_for(token, role=role, lang=lang)
        data = await self.raw.owned_card(token=token, role=selected, lang=lang)
        if raw:
            return data
        target = await self._owner_target(token, selected)
        return await self.builds.card(data, target, self._language(lang), scope="owner")

    async def owned_characters(
        self,
        token: str,
        *,
        role: Role | str | None = None,
        full: bool = False,
        lang: str | Language | None = None,
        raw: bool = False,
    ) -> list[CharacterBuild] | list[dict[str, Any]]:
        """Fetch the operator roster returned to the selected owner.

        Args:
            token: SKPORT account token belonging to the owner.
            role: Optional owner ``Role`` or ``3_<roleId>_<serverId>`` header.
            full: Fetch the individual detail endpoint for each returned operator.
            lang: Response and model language. Defaults to the configured language.
            raw: Return decoded character records and skip build normalization.

        Returns:
            A list of ``CharacterBuild`` models in roster order, or decoded
            character records when ``raw=True``.
        """
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
        token: str,
        *,
        char_id: str | None = None,
        name: str | None = None,
        index: int | None = None,
        operator_id: str | None = None,
        role: Role | str | None = None,
        full: bool = True,
        lang: str | Language | None = None,
        raw: bool = False,
    ) -> CharacterBuild | dict[str, Any]:
        """Fetch one operator from the selected owner's Endfield roster.

        Args:
            token: SKPORT account token belonging to the owner.
            char_id: Opaque operator ID returned by SKPORT.
            name: Localized operator name. Must match one returned operator.
            index: Zero-based index into the returned owner roster.
            operator_id: Optional service operator ID for the full detail request.
                The detail endpoint uses the selected character ID by default.
            role: Optional owner ``Role`` or ``3_<roleId>_<serverId>`` header.
            full: Fetch the individual operator detail. Set False to use the
                snapshot record.
            lang: Response and model language. Defaults to the configured language.
            raw: Return the selected service record and skip build normalization.

        Returns:
            A ``CharacterBuild``, or the selected decoded record when ``raw=True``.

        Raises:
            ConfigError: Exactly one of ``char_id``, ``name``, or ``index`` is
                required. Ambiguous names and invalid selectors also raise this.
            TargetNotFound: No owner role or operator matches the selection.
        """
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
        if card_data is None:
            card_data = await self.raw.owned_card(token=token, role=selected, lang=lang)
        target = await self._owner_target(token, selected)
        return (
            await self.builds.characters([record], self._player(target, card_data), self._language(lang))
        )[0]

    async def activity(
        self,
        skport_id: str | int,
        *,
        role_id: str | int | None = None,
        server_id: str | int | None = None,
        lang: str | Language | None = None,
    ) -> LiveStatus:
        """Fetch the resource and activity state exposed by a public game card.

        Args:
            skport_id: Public SKPORT community ID of the player.
            role_id: Endfield role ID to match when supplied.
            server_id: Endfield server ID to match when supplied.
            lang: Response language. Defaults to the configured language.

        Returns:
            ``LiveStatus`` with available resource meters, recovery timestamps,
            and activity state.
        """
        from skport.games.endfield.clean.progress import build_live_status

        data, target = await self._snapshot_data(skport_id, role_id, server_id, lang)
        return build_live_status(data, self._player(target, data), self.config.icon_source)

    async def owned_activity(
        self,
        token: str,
        *,
        role: Role | str | None = None,
        lang: str | Language | None = None,
    ) -> LiveStatus:
        """Fetch resource and activity state for the selected Endfield owner.

        Args:
            token: SKPORT account token belonging to the owner.
            role: Optional owner ``Role`` or ``3_<roleId>_<serverId>`` header.
            lang: Response language. Defaults to the configured language.

        Returns:
            ``LiveStatus`` with resource meters, recovery timestamps, and activity
            state from the authenticated game card.
        """
        from skport.games.endfield.clean.progress import build_live_status

        selected = await self.raw.role_for(token, role=role, lang=lang)
        data = await self.raw.owned_card(token=token, role=selected, lang=lang)
        target = await self._owner_target(token, selected)
        return build_live_status(data, self._player(target, data), self.config.icon_source)

    async def factory(
        self,
        skport_id: str | int,
        *,
        role_id: str | int | None = None,
        server_id: str | int | None = None,
        lang: str | Language | None = None,
    ) -> FactoryState:
        """Fetch public factory, exploration, and Dijiang state.

        Args:
            skport_id: Public SKPORT community ID of the player.
            role_id: Endfield role ID to match when supplied.
            server_id: Endfield server ID to match when supplied.
            lang: Response language. Defaults to the configured language.

        Returns:
            ``FactoryState`` with available region and area progress,
            settlements, Dijiang cabins, and crew.
        """
        from skport.games.endfield.clean.world import build_factory_state

        data, target = await self._snapshot_data(skport_id, role_id, server_id, lang)
        return build_factory_state(data, self._player(target, data), self.config.icon_source)

    async def monument(
        self,
        skport_id: str | int,
        *,
        role_id: str | int | None = None,
        server_id: str | int | None = None,
        lang: str | Language | None = None,
    ) -> MonumentState:
        """Fetch the player's public Monument records.

        Args:
            skport_id: Public SKPORT community ID of the player.
            role_id: Endfield role ID to match when supplied.
            server_id: Endfield server ID to match when supplied.
            lang: Response and model language. Defaults to the configured language.

        Returns:
            ``MonumentState`` with available events, stage completions, medals,
            and teams enriched by the exposed operator roster.
        """
        from skport.games.endfield.clean.endgame import build_monument_report

        data, target = await self._snapshot_data(skport_id, role_id, server_id, lang)
        detail = await self.raw.indie_hard(target, lang=lang)
        roster = await self.builds.characters(
            character_records(data, False),
            self._player(target, data),
            self._language(lang),
        )
        return build_monument_report(
            detail, self._player(target, data), self.config.icon_source, roster=roster
        )

    async def contract(
        self,
        skport_id: str | int,
        *,
        role_id: str | int | None = None,
        server_id: str | int | None = None,
        lang: str | Language | None = None,
    ) -> ContractState:
        """Fetch the player's public Contingency Contract records.

        Args:
            skport_id: Public SKPORT community ID of the player.
            role_id: Endfield role ID to match when supplied.
            server_id: Endfield server ID to match when supplied.
            lang: Response and model language. Defaults to the configured language.

        Returns:
            ``ContractState`` with available contracts, stage runs, modifiers,
            and teams enriched by the exposed operator roster.
        """
        from skport.games.endfield.clean.endgame import build_contract_report

        data, target = await self._snapshot_data(skport_id, role_id, server_id, lang)
        detail = await self.raw.crisis_contract(target, lang=lang)
        roster = await self.builds.characters(
            character_records(data, False),
            self._player(target, data),
            self._language(lang),
        )
        return build_contract_report(
            detail, self._player(target, data), self.config.icon_source, roster=roster
        )

    async def pulls(
        self,
        token: str,
        *,
        role: Role | str | None = None,
        lang: str | Language | None = None,
        since: PullHistory | None = None,
        after: datetime | None = None,
        featured_items: Mapping[tuple[str, str, int | None], Collection[str]] | None = None,
    ) -> PullHistory:
        """Fetch or refresh the selected owner's pull history.

        Args:
            token: SKPORT account token belonging to the owner.
            role: Optional owner ``Role`` or ``3_<roleId>_<serverId>`` header.
            lang: Response language. Defaults to the configured language.
            since: Previous history for this owner and role to extend. Use
                either ``since`` or ``after``.
            after: Exclusive, timezone-aware cutoff for pull times.
            featured_items: Optional verified featured item IDs keyed by
                ``(stream.key, banner_id, pool_version)``.

        Returns:
            ``PullHistory`` with observed records, stream checkpoints, and
            coverage and pity information supported by the available data.

        Raises:
            ConfigError: Both history inputs are supplied, the cutoff lacks a
                timezone, or the saved history belongs to another account or role.
        """
        return await self.raw.pulls.history(
            token=token, role=role, lang=lang, since=since, after=after, featured_items=featured_items
        )

    async def wiki_categories(
        self, *, lang: str | Language | None = None, ttl: float | None = _WIKI_TTL
    ) -> WikiCatalogTree:
        """Fetch the Endfield wiki's category and filter tree.

        Args:
            lang: Wiki language. Defaults to the configured language.
            ttl: Cache lifetime in seconds. Use 0 to bypass the cache.

        Returns:
            ``WikiCatalogTree`` with localized categories, subcategories, and
            their published filters.
        """
        from skport.games.endfield.clean.wiki import wiki_categories

        locale = self._language(lang)
        data = await self.raw.wiki_categories(lang=locale, ttl=ttl)
        return wiki_categories(data, self.config.icon_source, locale)

    async def wiki_catalog(
        self,
        *,
        type_sub_id: int | None = None,
        type_main_id: int = 1,
        lang: str | Language | None = None,
        ttl: float | None = _WIKI_TTL,
    ) -> list[WikiSummary]:
        """List the articles in a localized wiki category.

        Args:
            type_sub_id: Subcategory ID. Omit to list the entire main category.
            type_main_id: Main category ID. Defaults to 1, Endfield Database.
            lang: Wiki language. Defaults to the configured language.
            ttl: Cache lifetime in seconds. Use 0 to bypass the cache.

        Returns:
            A list of ``WikiSummary`` records with article IDs, names, artwork,
            and game associations when the catalog provides them.
        """
        from skport.games.endfield.clean.wiki import wiki_catalog

        data = await self.raw.wiki_catalog(
            type_sub_id=type_sub_id, type_main_id=type_main_id, lang=self._language(lang), ttl=ttl
        )
        return wiki_catalog(data, self.config.icon_source)

    async def wiki_search(
        self,
        keyword: str,
        *,
        category: tuple[int, int] | None = None,
        lang: str | Language | None = None,
        ttl: float | None = _WIKI_TTL,
    ) -> list[WikiSummary]:
        """Search published wiki articles using the service's search results.

        Args:
            keyword: Search text in the requested language.
            category: Optional ``(main_type_id, type_sub_id)`` filter applied
                locally to the returned matches.
            lang: Wiki language. Defaults to the configured language.
            ttl: Cache lifetime in seconds. Use 0 to bypass the cache.

        Returns:
            A list of ``WikiSummary`` matches in service order. An empty or
            whitespace-only keyword returns an empty list.
        """
        from skport.games.endfield.clean.wiki import wiki_search

        if not keyword.strip():
            return []
        data = await self.raw.wiki_search(keyword.strip(), lang=self._language(lang), ttl=ttl)
        results = wiki_search(data, self.config.icon_source)
        if category is not None:
            main_id, sub_id = map(str, category)
            results = [row for row in results if (row.main_type_id, row.sub_type_id) == (main_id, sub_id)]
        return results

    async def wiki_items(
        self,
        ids: Collection[str | int],
        *,
        lang: str | Language | None = None,
        ttl: float | None = _WIKI_TTL,
    ) -> WikiBatchResult:
        """Resolve exact wiki article IDs in batches of up to 30.

        Args:
            ids: Collection of nonempty wiki article IDs as strings or integers.
                Duplicate IDs are requested once.
            lang: Wiki language. Defaults to the configured language.
            ttl: Cache lifetime in seconds. Use 0 to bypass the cache.

        Returns:
            ``WikiBatchResult`` with summaries keyed by article ID, category
            metadata, and the IDs omitted by the endpoint.

        Raises:
            ConfigError: The collection or one of its article IDs is invalid.
        """
        from skport.games.endfield.clean.wiki import wiki_batch

        if isinstance(ids, (str, bytes)) or any(
            isinstance(key, bool) or not isinstance(key, (int, str)) or not str(key).strip() for key in ids
        ):
            raise ConfigError("ids must be a collection of nonempty wiki article IDs")
        locale = self._language(lang)
        keys = list(dict.fromkeys(str(key).strip() for key in ids))
        batches = [keys[i : i + _WIKI_BATCH_SIZE] for i in range(0, len(keys), _WIKI_BATCH_SIZE)]
        data = await asyncio.gather(*(self.raw.wiki_items(group, lang=locale, ttl=ttl) for group in batches))
        result = WikiBatchResult(locale=locale, requested_ids=keys)
        for group, payload in zip(batches, data, strict=True):
            batch = wiki_batch(payload, group, self.config.icon_source, locale)
            result.items.update(batch.items)
            result.missing_ids.extend(batch.missing_ids)
            result.main_categories.update(batch.main_categories)
            result.subcategories.update(batch.subcategories)
        return result

    async def wiki_index(
        self,
        *,
        categories: Collection[tuple[int, int]] | None = None,
        lang: str | Language | None = None,
        ttl: float | None = _WIKI_TTL,
    ) -> WikiIndex:
        """Build an index of wiki articles and their game associations.

        Args:
            categories: Optional collection of ``(main_type_id, type_sub_id)``
                pairs. Omit to discover and index all main categories.
            lang: Wiki language. Defaults to the configured language.
            ttl: Cache lifetime in seconds. Use 0 to bypass the cache.

        Returns:
            ``WikiIndex`` keyed by article ID, with category-scoped game ID
            lookup and issues for category requests that failed.
        """
        locale = self._language(lang)
        selections: list[tuple[int, int | None]]
        if categories is None:
            tree = await self.wiki_categories(lang=locale, ttl=ttl)
            selections = [(int(main.key), None) for main in tree.categories if main.key.isdecimal()]
        else:
            selections = list(dict.fromkeys(categories))
        results = await asyncio.gather(
            *(
                self.wiki_catalog(type_main_id=main, type_sub_id=sub, lang=locale, ttl=ttl)
                for main, sub in selections
            ),
            return_exceptions=True,
        )
        index = WikiIndex(locale=locale)
        for (main, sub), result in zip(selections, results, strict=True):
            if isinstance(result, SkportError):
                index.issues.append(_optional_lookup_issue(f"catalog.{main}.{sub or ''}", result))
            elif isinstance(result, BaseException):
                raise result
            else:
                index.items.update((row.id, row) for row in result)
        return index

    async def wiki_item(
        self,
        item_id: str | int,
        *,
        lang: str | Language | None = None,
        index: Mapping[str, WikiSummary] | None = None,
        ttl: float | None = _WIKI_TTL,
    ) -> WikiPage:
        """Fetch one published wiki article.

        Args:
            item_id: Wiki article ID from the catalog or search.
            lang: Wiki language. Defaults to the configured language.
            index: Optional summaries keyed by wiki article ID for resolving
                inline item links.
            ttl: Cache lifetime in seconds. Use 0 to bypass the cache.

        Returns:
            ``WikiPage`` with article metadata, ordered sections, media, tables,
            lists, and any parsing issues.

        Raises:
            WikiNotFound: The service has no article for this ID and language.
            DecodeError: The returned article is malformed.
        """
        from skport.games.endfield.clean.wiki import wiki_page

        data = await self.raw.wiki_item(item_id, lang=self._language(lang), ttl=ttl)
        return wiki_page(data, self.config.icon_source, index=index)

    async def _wiki_reference_page(
        self, item_id: str | int, lang: str, fallback_lang: str | Language | None, ttl: float | None
    ) -> WikiPage:
        try:
            return await self.wiki_item(item_id, lang=lang, ttl=ttl)
        except WikiNotFound:
            if fallback_lang is None or self._language(fallback_lang) == lang:
                raise
        return await self.wiki_item(item_id, lang=fallback_lang, ttl=ttl)

    async def wiki_operator(
        self,
        item_id: str | int,
        *,
        lang: str | Language | None = None,
        fallback_lang: str | Language | None = None,
        ttl: float | None = _WIKI_TTL,
    ) -> WikiOperatorReference:
        """Fetch a published operator reference from the wiki.

        Args:
            item_id: Wiki article ID in the Operators category.
            lang: Wiki language. Defaults to the configured language.
            fallback_lang: Language to try if the requested article is absent.
                Existing partial translations are returned in their own language.
            ttl: Cache lifetime in seconds. Use 0 to bypass the cache.

        Returns:
            ``WikiOperatorReference`` with profile fields, artwork, published
            base stats by level, and skill metrics by rank when available.

        Raises:
            ConfigError: The article is outside the Operators category.
            WikiNotFound: The article is unavailable in the selected language.
        """
        from skport.games.endfield.clean.wiki_operator import wiki_operator

        locale = self._language(lang)
        page = await self._wiki_reference_page(item_id, locale, fallback_lang, ttl)
        return wiki_operator(page, requested_locale=locale)

    async def wiki_upgrade_guide(
        self,
        item_id: str | int,
        *,
        lang: str | Language | None = None,
        fallback_lang: str | Language | None = None,
        ttl: float | None = _WIKI_TTL,
    ) -> WikiUpgradeGuide:
        """Fetch an operator's published upgrade steps and material costs.

        Args:
            item_id: Wiki article ID in the Operators category.
            lang: Wiki language. Defaults to the configured language.
            fallback_lang: Language to try if the requested article is absent.
                Existing partial translations are returned in their own language.
            ttl: Cache lifetime in seconds. Use 0 to bypass the cache.

        Returns:
            ``WikiUpgradeGuide`` with selectable steps, published cost options,
            source cells, and localized material summaries where available.
            Use ``total()`` to sum selected steps and identify unpriced costs.

        Raises:
            ConfigError: The article is outside the Operators category.
            WikiNotFound: The article is unavailable in the selected language.
        """
        from skport.games.endfield.clean.wiki_upgrade import wiki_upgrade_guide

        locale = self._language(lang)
        page = await self._wiki_reference_page(item_id, locale, fallback_lang, ttl)
        guide = wiki_upgrade_guide(page)
        guide.requested_locale = locale
        if guide.material_ids:
            try:
                batch = await self.wiki_items(guide.material_ids, lang=page.summary.locale or locale, ttl=ttl)
            except SkportError as exc:
                guide.issues.append(_optional_lookup_issue("materials", exc))
            else:
                guide = wiki_upgrade_guide(page, index=batch.items)
                guide.requested_locale = locale
                guide.issues.extend(batch.issues)
                guide.issues.extend(
                    ModelIssue(
                        code="wiki_material_summary_missing",
                        message="The batch returned no summary for a referenced material",
                        path=f"materials.{key}",
                    )
                    for key in batch.missing_ids
                )
        return guide

    async def wiki_material(
        self, item_id: str | int, *, lang: str | Language | None = None, ttl: float | None = _WIKI_TTL
    ) -> WikiMaterial:
        """Fetch a wiki article's material acquisition and usage information.

        Args:
            item_id: Wiki article ID of the material.
            lang: Wiki language. Defaults to the configured language.
            ttl: Cache lifetime in seconds. Use 0 to bypass the cache.

        Returns:
            ``WikiMaterial`` with available acquisition and usage sections,
            documented recipes, and any parsing issues.

        Raises:
            WikiNotFound: The article is unavailable in the selected language.
        """
        from skport.games.endfield.clean.wiki import wiki_material

        return wiki_material(await self.wiki_item(item_id, lang=lang, ttl=ttl))

    async def char_banners(
        self, *, lang: str | Language | None = None, ttl: float | None = _BANNER_TTL, enrich: bool = True
    ) -> list[Banner]:
        """Fetch published character banners from the wiki.

        Args:
            lang: Wiki language. Defaults to the configured language.
            ttl: Cache lifetime in seconds. Use 0 to bypass the cache.
            enrich: Resolve blank item names from their linked wiki articles.

        Returns:
            A list of ``Banner`` models with featured characters, available
            regional pool windows, and any enrichment issues.
        """
        return await self._wiki_banners("character", self._language(lang), ttl, enrich)

    async def weapon_banners(
        self, *, lang: str | Language | None = None, ttl: float | None = _BANNER_TTL, enrich: bool = True
    ) -> list[Banner]:
        """Fetch published weapon banners from the wiki.

        Args:
            lang: Wiki language. Defaults to the configured language.
            ttl: Cache lifetime in seconds. Use 0 to bypass the cache.
            enrich: Resolve blank item names from their linked wiki articles.

        Returns:
            A list of ``Banner`` models with featured weapons, available
            regional pool windows, and any enrichment issues.
        """
        return await self._wiki_banners("weapon", self._language(lang), ttl, enrich)

    async def _wiki_banners(
        self, kind: Literal["character", "weapon"], locale: str, ttl: float | None, enrich: bool
    ) -> list[Banner]:
        from skport.games.endfield.clean.wiki import banners

        fetch = self.raw.char_banners if kind == "character" else self.raw.weapon_banners
        result = banners(await fetch(lang=locale, ttl=ttl), kind=kind, preferred=self.config.icon_source)
        targets = [(banner, item) for banner in result for item in banner.items if item.wiki_id and not item.name]
        if enrich and targets:
            try:
                batch = await self.wiki_items(
                    [item.wiki_id for _, item in targets if item.wiki_id], lang=locale, ttl=ttl
                )
            except SkportError as exc:
                for banner in result:
                    if any(item.wiki_id and not item.name for item in banner.items):
                        banner.issues.append(_optional_lookup_issue("items", exc))
            else:
                sub_id = "1" if kind == "character" else "2"
                for banner, item in targets:
                    summary = batch.items.get(item.wiki_id or "")
                    if summary and (summary.main_type_id, summary.sub_type_id) == ("1", sub_id) and summary.name:
                        item.name = summary.name
                    else:
                        banner.issues.append(
                            ModelIssue(
                                code="wiki_banner_item_missing",
                                message="The linked article has no matching banner summary",
                                path=f"items.{item.id}",
                            )
                        )
        return result

    async def enums(self, *, lang: str | Language | None = None) -> EnumCatalog:
        """Fetch the game's localized enum catalog.

        Args:
            lang: Response language. Defaults to the configured language.

        Returns:
            ``EnumCatalog`` with available enum keys, labels, and artwork.
        """
        locale = self._language(lang)
        return enum_catalog(await self.raw.enums(lang=locale), locale, self.config.icon_source)

    async def news(self, *, lang: str | Language | None = None) -> list[Notice]:
        """Fetch the official Endfield news feed.

        Args:
            lang: Bulletin language. Defaults to the configured language.

        Returns:
            A list of ``Notice`` models with localized bulletin text and
            available artwork and links.
        """
        locale = self._language(lang)
        return notices(await self.raw.news(lang=locale), locale)

    @overload
    async def attendance(
        self, token: str, *, role: Role | str | None = None,
        lang: str | Language | None = None, raw: Literal[True] = True,
    ) -> dict[str, Any]: ...

    @overload
    async def attendance(
        self, token: str, *, role: Role | str | None = None,
        lang: str | Language | None = None, raw: Literal[False],
    ) -> AttendanceStatus: ...

    @overload
    async def attendance(
        self, token: str, *, role: Role | str | None = None,
        lang: str | Language | None = None, raw: bool,
    ) -> AttendanceStatus | dict[str, Any]: ...

    async def attendance(
        self,
        token: str,
        *,
        role: Role | str | None = None,
        lang: str | Language | None = None,
        raw: bool = True,
    ) -> AttendanceStatus | dict[str, Any]:
        """Fetch the selected owner's daily attendance calendar.

        Args:
            token: SKPORT account token belonging to the owner.
            role: Optional owner ``Role`` or ``3_<roleId>_<serverId>`` header.
            lang: Response language. Defaults to the configured language.
            raw: Return decoded service data by default. Set False for a model.

        Returns:
            The decoded calendar payload, or ``AttendanceStatus`` with
            available signed days and rewards when ``raw=False``.
        """
        data = await self.raw.attendance(token=token, role=role, lang=lang)
        return data if raw else attendance_status(data, self.config.icon_source)

    @overload
    async def check_in(
        self, token: str, *, role: Role | str | None = None,
        lang: str | Language | None = None, raw: Literal[True] = True,
    ) -> dict[str, Any]: ...

    @overload
    async def check_in(
        self, token: str, *, role: Role | str | None = None,
        lang: str | Language | None = None, raw: Literal[False],
    ) -> CheckInResult: ...

    @overload
    async def check_in(
        self, token: str, *, role: Role | str | None = None,
        lang: str | Language | None = None, raw: bool,
    ) -> CheckInResult | dict[str, Any]: ...

    async def check_in(
        self,
        token: str,
        *,
        role: Role | str | None = None,
        lang: str | Language | None = None,
        raw: bool = True,
    ) -> CheckInResult | dict[str, Any]:
        """Submit one daily attendance claim for the selected owner role.

        Args:
            token: SKPORT account token belonging to the owner.
            role: Optional owner ``Role`` or ``3_<roleId>_<serverId>`` header.
            lang: Response language. Defaults to the configured language.
            raw: Return decoded service data by default. Set False for a model.

        Returns:
            The decoded claim response, or ``CheckInResult`` with the returned
            rewards when ``raw=False``.

        Raises:
            AlreadyCheckedIn: The service reports an existing daily claim.
        """
        data = await self.raw.check_in(token=token, role=role, lang=lang)
        return data if raw else check_in_result(data, self.config.icon_source)

    @overload
    async def inventory(
        self, token: str, *, role: Role | str | None = None,
        lang: str | Language | None = None, raw: Literal[True] = True, enrich: bool = False,
    ) -> dict[str, Any]: ...

    @overload
    async def inventory(
        self, token: str, *, role: Role | str | None = None,
        lang: str | Language | None = None, raw: Literal[False], enrich: bool = False,
    ) -> Inventory: ...

    @overload
    async def inventory(
        self, token: str, *, role: Role | str | None = None,
        lang: str | Language | None = None, raw: bool, enrich: bool = False,
    ) -> Inventory | dict[str, Any]: ...

    async def inventory(
        self,
        token: str,
        *,
        role: Role | str | None = None,
        lang: str | Language | None = None,
        raw: bool = True,
        enrich: bool = False,
    ) -> Inventory | dict[str, Any]:
        """Fetch the operators, weapons, gear, and tacticals owned by an Endfield role.

        Args:
            token: SKPORT account token belonging to the owner.
            role: Optional owner ``Role`` or ``3_<roleId>_<serverId>`` header.
            lang: Response language. Defaults to the configured language.
            raw: Return decoded service data by default. Set False for a model.
            enrich: For typed output, fill available display metadata using
                the owner's card and wiki summaries.

        Returns:
            The decoded inventory payload, or ``Inventory`` with the reported
            ownership, counts, progression, and any enrichment issues.
        """
        if raw:
            return await self.raw.inventory(token=token, role=role, lang=lang)
        locale = self._language(lang)
        owner = await self.raw.role_for(token, role=role, lang=locale) if enrich else role
        data = await self.raw.inventory(token=token, role=owner, lang=locale)
        result = build_inventory(data, self.config.icon_source, lang=locale)
        if not enrich:
            return result
        return await self._enrich_inventory(result, token=token, role=owner, locale=locale)

    async def _enrich_inventory(
        self, result: Inventory, *, token: str, role: Role | str | None, locale: str
    ) -> Inventory:
        sources = (
            ("owner_card", self.raw.owned_card(token=token, role=role, lang=locale)),
            ("operator_catalog", self.wiki_catalog(type_sub_id=1, lang=locale)),
            ("weapon_catalog", self.wiki_catalog(type_sub_id=2, lang=locale)),
        )
        metadata = await asyncio.gather(*(fetch for _, fetch in sources), return_exceptions=True)
        owner_card: Any = None
        catalog: list[WikiSummary] = []
        for (source, _), payload in zip(sources, metadata, strict=True):
            if isinstance(payload, SkportError):
                result.issues.append(_optional_lookup_issue(source, payload))
            elif isinstance(payload, BaseException):
                raise payload
            elif source == "owner_card":
                owner_card = payload
            else:
                catalog.extend(payload)
        ids = inventory_wiki_ids(result, owner_card) - {row.id for row in catalog}
        summaries: dict[str, WikiSummary] = {}
        if ids:
            try:
                summaries = (await self.wiki_items(sorted(ids), lang=locale)).items
            except SkportError as exc:
                result.issues.append(_optional_lookup_issue("wiki_batch", exc))
        return enrich_inventory(
            result, self.config.icon_source, lang=locale, owner_card=owner_card, catalog=catalog, summaries=summaries
        )

    async def _owner_target(self, token: str, role: Role) -> Target:
        credential = await self.api.pool.credential_for(token)
        return Target(credential.user_id, role.role_id, role.server_id)

    async def _snapshot_data(
        self,
        skport_id: str | int,
        role_id: str | int | None,
        server_id: str | int | None,
        lang: str | Language | None,
    ) -> tuple[dict[str, Any], Target]:
        target = await self.resolve(skport_id, role_id=role_id, server_id=server_id, lang=lang)
        return await self.raw.detail(target, lang=lang), target

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
