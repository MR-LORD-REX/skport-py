"""Registration and lazy construction of game-specific clients."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from skport.errors import ConfigError
from skport.games.base import Game, GameClient

if TYPE_CHECKING:
    from skport.api import SkportAPI

GameFactory = Callable[["SkportAPI"], GameClient]


def _game_name(value: Game | str) -> str:
    name = str(value).strip().lower()
    if not name:
        raise ConfigError("A game name cannot be empty")
    return name


class GameRegistry:
    """Retain one client per game, with no closed enumeration requirement."""

    def __init__(self) -> None:
        self._factories: dict[str, GameFactory] = {}
        self._instances: dict[str, GameClient] = {}

    def register(self, game: Game | str, factory: GameFactory, *, replace: bool = False) -> None:
        """Register a factory before its game client is instantiated."""
        key = _game_name(game)
        if key in self._instances:
            raise ConfigError(f"Close the active {key!r} client before replacing its factory")
        if key in self._factories and not replace:
            raise ConfigError(f"Game {key!r} is already registered")
        self._factories[key] = factory

    def create(self, game: Game | str, api: SkportAPI) -> GameClient:
        """Return the cached client for a registered game name."""
        key = _game_name(game)
        if key not in self._instances:
            try:
                factory = self._factories[key]
            except KeyError as exc:
                raise ConfigError(f"Unsupported game {key!r}; register a client factory first") from exc
            self._instances[key] = factory(api)
        return self._instances[key]

    async def close(self) -> None:
        """Close all game clients and retain registrations for later reuse."""
        clients = tuple(self._instances.values())
        self._instances.clear()
        first_error: Exception | None = None
        for client in clients:
            try:
                await client.close()
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error

    @property
    def names(self) -> tuple[str, ...]:
        """Return normalized names of registered game modules."""
        return tuple(sorted(self._factories))
