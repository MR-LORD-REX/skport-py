"""Validated metadata for immutable canonical asset snapshots."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from skport.errors import AssetError

STORE_TABLES = (
    "avatars",
    "weapons",
    "weapon_meta",
    "skills",
    "equips",
    "gems",
    "locs",
    "pfps",
    "namecards",
    "medals",
)
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
MAX_ASSET_BYTES = 8 * 1024 * 1024


def utc_timestamp() -> str:
    """Return an unambiguous acquisition timestamp for snapshot provenance."""
    return datetime.now(UTC).isoformat()


def parse_json(payload: bytes | str, label: str) -> dict[str, Any]:
    """Reject duplicate keys, non-finite numbers, and non-object asset roots."""

    def pairs(entries: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in entries:
            if key in result:
                raise AssetError(f"duplicate JSON key in {label}")
            result[key] = value
        return result

    def constant(_: str) -> None:
        raise AssetError(f"non-finite JSON number in {label}")

    try:
        decoded = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
        data = json.loads(decoded, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssetError(f"invalid asset JSON in {label}") from exc
    if not isinstance(data, dict):
        raise AssetError(f"asset root must be an object: {label}")
    pending: list[Any] = [data]
    while pending:
        value = pending.pop()
        if isinstance(value, float) and not math.isfinite(value):
            raise AssetError(f"non-finite JSON number in {label}")
        if isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return data


def validate_tables(tables: dict[str, dict[str, Any]]) -> None:
    """Check the original store boundaries needed by identity and calculation."""
    if set(tables) != set(STORE_TABLES):
        raise AssetError("asset snapshot does not contain all Endfield store tables")
    required = {
        "equips": ("Items", "Suits"),
        "gems": ("TermNums", "TemplateItems"),
        "weapon_meta": ("LevelCurves", "BreakSkillLevelBounds", "TalentSkillLevelBounds"),
    }
    for name, data in tables.items():
        if not isinstance(data, dict) or not data:
            raise AssetError(f"empty or invalid canonical asset table: {name}")
        if any(not isinstance(value, dict) for value in data.values()):
            raise AssetError(f"canonical asset entries must be objects: {name}")
        for key in required.get(name, ()):
            if not isinstance(data.get(key), dict):
                raise AssetError(f"canonical asset table is missing {name}.{key}")
            if name in ("equips", "gems") and any(
                not isinstance(entry, dict) for entry in data[key].values()
            ):
                raise AssetError(f"canonical asset entries must be objects: {name}.{key}")
    if not isinstance(tables["locs"].get("en"), dict):
        raise AssetError("canonical localization table is missing English fallback")
    skills = tables["skills"]
    curves = tables["weapon_meta"]["LevelCurves"]
    for weapon in tables["weapons"].values():
        curve = weapon.get("LevelTemplateId")
        if curve is not None and str(curve) not in curves:
            raise AssetError("canonical weapon references a missing level curve")
        if any(str(skill) not in skills for skill in weapon.get("SkillList", ())):
            raise AssetError("canonical weapon references a missing skill")
    suits = tables["equips"]["Suits"]
    for item in tables["equips"]["Items"].values():
        suit = item.get("SuitId")
        if suit and str(suit) not in suits:
            raise AssetError("canonical equipment references a missing suit")
    for suit in suits.values():
        skill = suit.get("SkillId")
        if skill is not None and str(skill) not in skills:
            raise AssetError("canonical suit references a missing skill")


def git_blob_sha(payload: bytes) -> str:
    """Calculate the Git blob identity used by the official source tree."""
    return hashlib.sha1(f"blob {len(payload)}\0".encode("ascii") + payload).hexdigest()


@dataclass(frozen=True, slots=True)
class AssetSnapshot:
    """A coherent official commit and its unmodified decoded store tables."""

    revision: str
    tables: dict[str, dict[str, Any]]
    fetched_at: str

    def table(self, name: str) -> dict[str, Any]:
        """Return a canonical table or a typed error for an unknown table name."""
        try:
            return self.tables[name]
        except KeyError as exc:
            raise AssetError(f"unknown canonical asset table: {name}") from exc

    def __getitem__(self, name: str) -> dict[str, Any]:
        return self.table(name)


@dataclass(frozen=True, slots=True)
class AssetUpdate:
    """The installed snapshot and whether its source commit changed."""

    snapshot: AssetSnapshot
    changed: bool
    previous_revision: str | None = None

    @property
    def revision(self) -> str:
        """The immutable official commit used by the installed snapshot."""
        return self.snapshot.revision
