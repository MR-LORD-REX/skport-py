"""Shared wire-to-output helpers without network access or game arithmetic."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any

from skport.assets import enka_image
from skport.config import ImageSource
from skport.errors import DecodeError
from skport.games.endfield.models.images import ImageLinks, SemanticLabel
from skport.games.endfield.models.stats import format_percent

_MARKUP = re.compile(r"<(?:[@#][^>]+|/)>|</?(?:color|b|i)(?:=[^>]*)?>")
_PARAMETER = re.compile(r"\{([A-Za-z0-9_]+)(?::([^}]+))?\}")


def wire_object(value: Any, source: str) -> dict[str, Any]:
    """Require a JSON object at a response boundary."""
    if not isinstance(value, dict):
        raise DecodeError(f"{source} must be an object")
    return value


def wire_list(value: Any, source: str) -> list[Any]:
    """Require a JSON array at a response boundary."""
    if not isinstance(value, list):
        raise DecodeError(f"{source} must be an array")
    return value


def image_links(
    skport: str | None = None, enka: str | None = None,
    preferred: ImageSource = ImageSource.SKPORT,
) -> ImageLinks:
    """Keep both artwork candidates and resolve only canonical Enka paths."""
    return ImageLinks(skport=skport or None, enka=enka_image(enka), preferred=preferred)


def numeric(value: Any, default: float = 0) -> float:
    """Read an explicit wire number, rejecting non-finite or malformed values."""
    if value is None or value == "":
        return default
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise DecodeError("expected a numeric game-data field") from exc
    if not math.isfinite(result):
        raise DecodeError("game-data number is not finite")
    return result


def timestamp(value: Any, *, milliseconds: bool = False) -> datetime | None:
    """Convert an explicit Unix timestamp; zero and empty fields mean missing."""
    if value is None or value == "" or numeric(value) == 0:
        return None
    seconds = numeric(value) / (1000 if milliseconds else 1)
    try:
        return datetime.fromtimestamp(seconds, UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise DecodeError("game-data timestamp is outside its supported range") from exc


def rarity(value: Any) -> int:
    """Read stable rarity keys without parsing translated color names."""
    key = value.get("key", "") if isinstance(value, dict) else str(value or "")
    match = re.search(r"(\d+)$", key)
    return int(match[1]) if match else 0


def semantic(value: Any, preferred: ImageSource = ImageSource.SKPORT) -> SemanticLabel:
    """Retain the stable enum key and the service's localized display label."""
    if isinstance(value, dict):
        return SemanticLabel(
            key=str(value.get("key") or ""), name=str(value.get("value") or ""),
            icons=image_links(value.get("iconUrl") or value.get("icon"), preferred=preferred),
        )
    return SemanticLabel(key=str(value or ""), name=str(value or ""))


def description(text: str, params: dict[str, Any] | None = None) -> str:
    """Render parameter metadata; a percent placeholder defines the unit."""
    values = params or {}

    def replace(match: re.Match[str]) -> str:
        key, formatting = match.groups()
        if key not in values:
            return match.group(0)
        value = values[key]
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return str(value)
        if formatting and "%" in formatting:
            return format_percent(amount, 0 if "." not in formatting else 1)
        return f"{amount:g}"

    return _MARKUP.sub("", _PARAMETER.sub(replace, text or ""))
