"""Shared asset-backed assembly for public and owner character data."""

from __future__ import annotations

from typing import Any, Literal

from skport.api import SkportAPI
from skport.assets import AssetManager, AssetSnapshot
from skport.config import ClientConfig, MissingAssetPolicy, parse_language
from skport.errors import AssetError, MappingError, SkportError
from skport.games.endfield.clean.character import build_character
from skport.games.endfield.clean.profile import build_player_card
from skport.games.endfield.identity import Target
from skport.games.endfield.models import CharacterBuild, ModelIssue, PlayerCard, PlayerIdentity


class BuildService:
    """Resolve one coherent asset snapshot for all builds in a player response."""

    def __init__(self, api: SkportAPI, assets: AssetManager, config: ClientConfig) -> None:
        self.api = api
        self.assets = assets
        self.config = config
        self._refreshed_revision: str | None = None

    async def _snapshot(self) -> tuple[AssetSnapshot | None, ModelIssue | None]:
        """Retain renderable wire data when canonical assets are unavailable."""
        try:
            return await self.assets.ensure(), None
        except AssetError as exc:
            if self.config.missing_assets is MissingAssetPolicy.RAISE:
                raise
            return None, ModelIssue(code=type(exc).__name__, message=str(exc))

    async def _labels(self, locale: str) -> dict[str, str]:
        """Use stable enum keys for localized equipment labels when available."""
        try:
            enums = await self.api.endfield.enums(lang=locale)
        except SkportError:
            return {}
        return {
            str(entry["key"]): str(entry.get("value") or "")
            for entries in enums.values()
            if isinstance(entries, list)
            for entry in entries
            if isinstance(entry, dict) and entry.get("key")
        }

    async def characters(
        self,
        records: list[dict[str, Any]],
        owner: PlayerIdentity,
        locale: str,
    ) -> list[CharacterBuild]:
        """Build public and owned characters through exactly the same pipeline."""
        if not records:
            return []
        snapshot, issue = await self._snapshot()
        labels = await self._labels(locale)

        def assemble(current: AssetSnapshot | None) -> list[CharacterBuild]:
            return [
                build_character(
                    raw,
                    current,
                    self.config,
                    owner=owner,
                    locale=locale,
                    labels=labels,
                    asset_issue=issue,
                )
                for raw in records
            ]

        try:
            builds = assemble(snapshot)
        except MappingError:
            if not await self._refresh_mapping(snapshot):
                raise
            return assemble(self.assets.current)
        missing = any(any(problem.code == "MappingError" for problem in build.issues) for build in builds)
        if missing and await self._refresh_mapping(snapshot):
            return assemble(self.assets.current)
        return builds

    async def _refresh_mapping(self, snapshot: AssetSnapshot | None) -> bool:
        """Refresh once per revision when an otherwise valid entity is missing."""
        if snapshot is None or self.config.assets_offline or not self.config.assets_auto_update:
            return False
        if self._refreshed_revision == snapshot.revision:
            return False
        self._refreshed_revision = snapshot.revision
        try:
            update = await self.assets.update()
        except AssetError:
            return False
        return update.changed

    async def card(
        self,
        data: dict[str, Any],
        target: Target,
        locale: str,
        scope: Literal["public", "owner"] = "public",
    ) -> PlayerCard:
        """Normalize one player snapshot, preserving ownership versus exposure."""
        from skport.games.endfield.selection import character_records

        base = (data.get("detail") or {}).get("base") or {}
        owner = PlayerIdentity(
            skport_id=target.user_id,
            game_uid=target.role_id,
            server_id=target.server_id,
            name=str(base.get("name") or ""),
        )
        builds = await self.characters(character_records(data, False), owner, locale)
        card = build_player_card(data, builds, target, locale, self.config.icon_source)
        card.source_scope = scope
        if "charNum" in base:
            card.roster_complete = card.counts.characters == len(builds)
        return card

    def language(self, value: str | None) -> str:
        """Normalize a per-call language without mutating shared credentials."""
        return parse_language(value or self.config.lang).value
