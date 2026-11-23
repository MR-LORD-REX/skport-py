"""Selection of raw character records without conflating names and IDs."""

from __future__ import annotations

import unicodedata
from typing import Any

from skport.errors import ConfigError, DecodeError, TargetNotFound


def character_records(data: dict[str, Any], showcase_only: bool) -> list[dict[str, Any]]:
    """Read exposed character records and optionally apply showcase ordering."""
    detail = data.get("detail")
    if not isinstance(detail, dict):
        raise DecodeError("The card endpoint did not return a detail object")
    chars = detail.get("chars")
    if not isinstance(chars, list) or any(not isinstance(char, dict) for char in chars):
        raise DecodeError("The card detail did not return a character list")
    if not showcase_only:
        return chars
    config = detail.get("config")
    if not isinstance(config, dict) or not isinstance(config.get("charIds"), list):
        raise DecodeError("The card did not include configured showcase character IDs")
    by_id = {str(char.get("id", "")): char for char in chars}
    return [by_id[str(char_id)] for char_id in config["charIds"] if str(char_id) in by_id]


def _name_key(name: str) -> str:
    return unicodedata.normalize("NFKC", name).casefold().strip()


def select_character(
    records: list[dict[str, Any]],
    *,
    char_id: str | None = None,
    name: str | None = None,
    index: int | None = None,
) -> dict[str, Any]:
    """Select a unique raw record by explicit ID, localized name, or position."""
    if index is not None:
        if isinstance(index, bool) or not isinstance(index, int):
            raise ConfigError("A character index must be an integer")
        if index < 0 or index >= len(records):
            raise TargetNotFound(f"Character index {index!r} is outside the returned list")
        return records[index]
    if char_id is not None:
        matches = [char for char in records if str(char.get("id")) == char_id]
    else:
        key = _name_key(name or "")
        if not key:
            raise ConfigError("A character name cannot be empty")
        matches = [
            char for char in records if _name_key(str((char.get("charData") or {}).get("name", ""))) == key
        ]
    if not matches:
        raise TargetNotFound("No returned character matches the supplied selector")
    if len(matches) != 1:
        raise ConfigError("The selector matches multiple characters; use an explicit char_id")
    return matches[0]
