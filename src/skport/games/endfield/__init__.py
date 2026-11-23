"""Endfield support without eagerly importing the game facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from skport.games.endfield.identity import Role, Target

if TYPE_CHECKING:
    from skport.games.endfield.client import EndfieldClient

__all__ = ["EndfieldClient", "Role", "Target"]


def __getattr__(name: str) -> Any:
    if name == "EndfieldClient":
        from skport.games.endfield.client import EndfieldClient

        return EndfieldClient
    raise AttributeError(name)
