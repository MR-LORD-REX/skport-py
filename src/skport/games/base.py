"""The small interface shared by independently implemented game clients."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from skport.api import SkportAPI


class Game(StrEnum):
    """Built-in game names; the registry also accepts custom string names."""

    ENDFIELD = "endfield"


class GameClient(Protocol):
    """A game module borrowing the facade's shared API."""

    game: Game | str
    api: SkportAPI

    async def close(self) -> None:
        """Release game-specific resources without closing the shared API."""
        ...
