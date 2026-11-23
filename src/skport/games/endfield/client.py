"""Raw-data conveniences for Endfield over the shared SKPORT API."""

from __future__ import annotations

import asyncio
from typing import Any

from skport.api import SkportAPI
from skport.config import Language
from skport.errors import ConfigError, DecodeError
from skport.games.base import Game
from skport.games.endfield.identity import Role, Target
from skport.games.endfield.selection import character_records, select_character


class EndfieldClient:
    """Fetch Endfield data without building models or calculating stats.

    This object borrows its API. Use ``raw`` for endpoint-level responses and
    the character helpers for explicit ID, localized name, or list index
    selection. Enka asset resolution belongs to a later phase.
    """

    game: Game | str = Game.ENDFIELD

    def __init__(self, api: SkportAPI) -> None:
        self.api = api
        self.raw = api.endfield

    async def __aenter__(self) -> EndfieldClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Release game resources; ownership of the shared API stays outside."""

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
        """Fetch the public SKPORT social profile in the requested language."""
        return await self.api.user(skport_id=skport_id, lang=lang)

    async def card(
        self,
        *,
        skport_id: str | int,
        role_id: str | int | None = None,
        server_id: str | int | None = None,
        lang: str | Language | None = None,
    ) -> dict[str, Any]:
        """Fetch the raw Endfield card data, including its ``detail`` field."""
        target = await self.resolve(skport_id, role_id=role_id, server_id=server_id, lang=lang)
        return await self.raw.detail(target, lang=lang)

    async def characters(
        self,
        *,
        skport_id: str | int,
        role_id: str | int | None = None,
        server_id: str | int | None = None,
        showcase_only: bool = False,
        full: bool = False,
        lang: str | Language | None = None,
    ) -> list[dict[str, Any]]:
        """Return card character records, optionally in configured showcase order.

        ``detail.chars`` contains the records the public endpoint exposes.
        ``showcase_only=True`` restricts them to ``detail.config.charIds``.
        ``full=True`` requests the individual build endpoint for each record.
        """
        target = await self.resolve(skport_id, role_id=role_id, server_id=server_id, lang=lang)
        records = character_records(await self.raw.detail(target, lang=lang), showcase_only)
        if not full:
            return records
        responses = await asyncio.gather(
            *(self.raw.character(target, char_id=str(item["id"]), lang=lang) for item in records)
        )
        return [_character_detail(response) for response in responses]

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
    ) -> dict[str, Any]:
        """Fetch a character using exactly one of ``char_id``, ``name``, or ``index``.

        Names match the response language and must be unique after Unicode
        normalization. Indexes refer to the card order, or showcase order when
        selected explicitly. A direct ID avoids downloading the card first.
        """
        if sum(value is not None for value in (char_id, name, index)) != 1:
            raise ConfigError("Supply exactly one of char_id=, name=, or index=")
        if char_id is not None and not char_id:
            raise ConfigError("char_id cannot be empty")
        target = await self.resolve(skport_id, role_id=role_id, server_id=server_id, lang=lang)
        if char_id is None or not full:
            records = character_records(await self.raw.detail(target, lang=lang), showcase_only)
            selected = select_character(records, char_id=char_id, name=name, index=index)
            if not full:
                return selected
            char_id = str(selected["id"])
        return _character_detail(await self.raw.character(target, char_id=char_id, lang=lang))

    async def attendance(
        self, *, token: str, role: Role | str | None = None, lang: str | Language | None = None
    ) -> dict[str, Any]:
        """Read attendance using the explicitly supplied account's token."""
        return await self.raw.attendance(token=token, role=role, lang=lang)

    async def check_in(
        self, *, token: str, role: Role | str | None = None, lang: str | Language | None = None
    ) -> dict[str, Any]:
        """Claim daily attendance for the explicitly supplied account."""
        return await self.raw.check_in(token=token, role=role, lang=lang)

    async def inventory(
        self, *, token: str, role: Role | str | None = None, lang: str | Language | None = None
    ) -> dict[str, Any]:
        """Read inventory using the explicitly supplied account's token."""
        return await self.raw.inventory(token=token, role=role, lang=lang)


def _character_detail(response: dict[str, Any]) -> dict[str, Any]:
    detail = response.get("detail")
    if not isinstance(detail, dict):
        raise DecodeError("The character endpoint did not return a detail object")
    return detail
