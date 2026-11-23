"""The multi-game facade and ownership of shared API resources."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from skport.api import SkportAPI
from skport.config import ClientConfig, Language, Region, parse_language, parse_region
from skport.errors import ConfigError
from skport.games.base import Game, GameClient
from skport.games.endfield.client import EndfieldClient
from skport.games.registry import GameRegistry


class SkportClient:
    """Compose game clients over one reusable SKPORT API.

    Supply ``api=`` to share a token pool across clients, or ``tokens=`` to let
    this facade create and own the API. Closing a facade never closes an API
    supplied by the caller.
    """

    def __init__(
        self,
        api: SkportAPI | None = None,
        *,
        tokens: list[str] | None = None,
        config: ClientConfig | None = None,
        lang: str | Language | None = None,
        region: str | Region | None = None,
    ) -> None:
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
        self._closed = False
        self.registry = GameRegistry()
        self.registry.register(Game.ENDFIELD, EndfieldClient)

    async def __aenter__(self) -> SkportClient:
        """Enter the facade without authenticating until needed."""
        self._require_open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    @property
    def endfield(self) -> EndfieldClient:
        """Return the cached Endfield client sharing this API."""
        return cast(EndfieldClient, self.game(Game.ENDFIELD))

    def game(self, game: Game | str) -> GameClient:
        """Return a registered game client, creating it on first access."""
        self._require_open()
        return self.registry.create(game, self.api)

    async def warm(self) -> None:
        """Authenticate the token pool before the first application request."""
        self._require_open()
        await self.api.warm()

    async def close(self) -> None:
        """Release game clients and close an API created by this facade."""
        if self._closed:
            return
        self._closed = True
        try:
            await self.registry.close()
        finally:
            if self._owns_api:
                await self.api.close()

    def _require_open(self) -> None:
        if self._closed:
            raise ConfigError("This SkportClient is closed")
