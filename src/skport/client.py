"""The multi-game facade and ownership of shared API resources."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from skport.api import SkportAPI
from skport.assets import AssetManager, AssetUpdate
from skport.config import ClientConfig, ImageSource, Language, Region, parse_language, parse_region
from skport.errors import ConfigError
from skport.games.base import Game, GameClient
from skport.games.endfield.client import EndfieldClient
from skport.games.registry import GameRegistry


class SkportClient:
    """Use one SKPORT API to access registered game clients.

    Use ``client.endfield`` for Endfield operations and ``game()`` for other
    registered clients. Use ``async with SkportClient(...)`` to release the
    resources created by the client when finished.
    """

    def __init__(
        self,
        api: SkportAPI | None = None,
        *,
        tokens: list[str] | None = None,
        config: ClientConfig | None = None,
        lang: str | Language | None = None,
        region: str | Region | None = None,
        icon_source: str | ImageSource | None = None,
        assets: AssetManager | None = None,
    ) -> None:
        """Create a client from an existing API or a list of account tokens.

        Args:
            api: Existing ``SkportAPI`` to share across clients. The caller
                manages its lifetime.
            tokens: Nonempty list of account tokens for a client-created API.
            config: API settings used when constructing an API from tokens.
            lang: Default request language for a client-created API. Overrides
                the language in ``config`` when supplied.
            region: Deployment for a client-created API. Only the global
                deployment is supported.
            icon_source: Preferred source for artwork in normalized results.
            assets: Existing ``AssetManager`` to share with game clients. The
                caller manages its lifetime.

        Raises:
            ConfigError: Neither data source was supplied, ``api`` was combined
                with ``tokens``, ``config``, ``lang`` or ``region``, or a setting
                is invalid.
        """
        try:
            preferred_icons = ImageSource(icon_source) if icon_source is not None else None
        except ValueError as exc:
            raise ConfigError("unsupported image source") from exc
        if api is not None:
            if tokens is not None or config is not None or lang is not None or region is not None:
                raise ConfigError("Supply api= or tokens/config/lang/region, not both")
            self.api = api
        else:
            if not tokens:
                raise ConfigError("SkportClient requires api= or a non-empty tokens= list")
            settings = config or ClientConfig()
            if lang is not None:
                settings = replace(settings, lang=parse_language(lang))
            if region is not None:
                settings = replace(settings, region=parse_region(region))
            self.api = SkportAPI(tokens, config=settings)
        self._owns_api = api is None
        self.config = self.api.config
        if preferred_icons is not None:
            self.config = replace(self.config, icon_source=preferred_icons)
        self._assets = assets
        self._owns_assets = assets is None
        self._closed = False
        self.registry = GameRegistry()
        self.registry.register(
            Game.ENDFIELD,
            lambda shared_api: EndfieldClient(shared_api, assets=self.assets, config=self.config),
        )

    async def __aenter__(self) -> SkportClient:
        """Return this client for an ``async with`` block.

        Network authentication begins on the first request or a call to ``warm()``.
        """
        self._require_open()
        return self

    async def __aexit__(self, *_: object) -> None:
        """Release client resources when the context ends."""
        await self.close()

    @property
    def endfield(self) -> EndfieldClient:
        """Return the Endfield client backed by the shared SKPORT API."""
        return cast(EndfieldClient, self.game(Game.ENDFIELD))

    @property
    def assets(self) -> AssetManager:
        """Return the shared manager for Enka game data and artwork."""
        if self._assets is None:
            self._assets = AssetManager(self.config, self.api.transport)
        return self._assets

    async def update_assets(self) -> AssetUpdate:
        """Update the Enka game-data snapshot used by game clients.

        Returns:
            ``AssetUpdate`` with the installed snapshot and whether its source
            revision changed.

        Raises:
            AssetError: Updates are unavailable in offline mode, or loading or
                validating the upstream assets failed.
            ConfigError: The client is closed.
        """
        self._require_open()
        return await self.assets.update()

    def game(self, game: Game | str) -> GameClient:
        """Get a client for a registered game.

        Args:
            game: A built-in ``Game`` member or a registered game name.

        Returns:
            The game's client, created on first access and reused thereafter.

        Raises:
            ConfigError: The game is unregistered or the client is closed.
        """
        self._require_open()
        return self.registry.create(game, self.api)

    async def warm(self) -> None:
        """Authenticate public pool accounts concurrently before serving requests.

        Raises:
            PoolExhausted: The pool has no account available to serve a request.
            ConfigError: The client or its API is closed.
        """
        self._require_open()
        await self.api.warm()

    async def close(self) -> None:
        """Release the game clients and any API or asset manager created here.

        This method is safe to call more than once.
        """
        if self._closed:
            return
        self._closed = True
        try:
            await self.registry.close()
        finally:
            if self._owns_assets and self._assets is not None:
                await self._assets.close()
            if self._owns_api:
                await self.api.close()

    def _require_open(self) -> None:
        if self._closed:
            raise ConfigError("This SkportClient is closed")
