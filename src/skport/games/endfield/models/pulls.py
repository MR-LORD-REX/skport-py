"""Normalized pull records and portable, owner-scoped history."""

from __future__ import annotations

import csv
import json
import os
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import IO, Any, Literal

from pydantic import AwareDatetime, Field

from skport.games.endfield.models.base import ModelIssue, OutputModel
from skport.games.endfield.models.identity import PlayerIdentity
from skport.games.endfield.models.item import ItemSummary

_CSV_FIELDS = (
    "sequence_id", "stream_kind", "stream_pool", "kind", "item_id", "item_name", "banner_id",
    "banner_name", "pool_version", "rarity", "pulled_at", "is_draw", "is_free", "is_new", "count",
    "pity_at_drop",
)
_JSON_VERSION = 1


class PullStream(OutputModel):
    """One game-record stream with its own sequence and continuation cursor."""

    kind: Literal["character", "weapon"]
    pool_id: str = Field(min_length=1)

    @property
    def key(self) -> str:
        """Identify this stream across pages and saved histories."""
        return f"{self.kind}:{self.pool_id}"


class PullCheckpoint(OutputModel):
    """Newest observed sequence and the start of subsequent observed coverage."""

    stream: PullStream
    sequence_id: str | None = None
    covered_from: AwareDatetime | None = None
    reached_end: bool = False


class PullPool(OutputModel):
    """A weapon pool from the selected owner's game records."""

    id: str = Field(min_length=1)
    name: str = ""
    pool_type: str | None = None
    online: bool | None = None


class PullRecord(OutputModel):
    """One observed draw or gift with independent banner and item identity."""

    id: str = ""
    sequence_id: str = ""
    kind: str = ""
    stream: PullStream | None = None
    item: ItemSummary = Field(default_factory=ItemSummary)
    banner_id: str = ""
    banner_name: str = ""
    pool_version: int | None = Field(default=None, ge=0)
    rarity: int | None = Field(default=None, ge=0)
    pulled_at: AwareDatetime | None = None
    is_draw: bool = True
    is_free: bool | None = False
    is_new: bool | None = None
    count: int = Field(default=1, ge=1)
    pity_at_drop: int | None = Field(default=None, ge=0)


class PullPage(OutputModel):
    """A normalized page that preserves the service continuation contract."""

    records: list[PullRecord] = Field(default_factory=list)
    has_more: bool = False
    next_cursor: str | None = None
    owner: PlayerIdentity | None = None


class BannerPity(OutputModel):
    """Pity policy and observed progress, with unknown values represented by None."""

    banner_id: str = ""
    name: str = ""
    stream: PullStream | None = None
    pool_version: int | None = Field(default=None, ge=0)
    hard_scope: str | None = None
    current: int | None = Field(default=None, ge=0)
    observed_since_six_star: int = Field(default=0, ge=0)
    hard_limit: int | None = Field(default=None, ge=0)
    featured_guarantee: int | None = Field(default=None, ge=0)
    featured_item_ids: list[str] = Field(default_factory=list)
    featured_received: bool | None = None
    selector_limit: int | None = Field(default=None, ge=0)
    total: int = Field(default=0, ge=0)


class PullTotals(OutputModel):
    """Counts for the supplied history window, independent from pity totals."""

    character_draws: int = Field(default=0, ge=0)
    weapon_draws: int = Field(default=0, ge=0)
    free_draws: int = Field(default=0, ge=0)
    six_star_draws: int = Field(default=0, ge=0)
    gifts: int = Field(default=0, ge=0)


class PullHistory(OutputModel):
    """Records and optional pity state without implying complete account history."""

    player: PlayerIdentity
    records: list[PullRecord] = Field(default_factory=list)
    pools: list[PullPool] = Field(default_factory=list)
    checkpoints: list[PullCheckpoint] = Field(default_factory=list)
    pity: list[BannerPity] = Field(default_factory=list)
    totals: PullTotals = Field(default_factory=PullTotals)
    from_time: AwareDatetime | None = None
    to_time: AwareDatetime | None = None
    complete_history: bool = False
    issues: list[ModelIssue] = Field(default_factory=list)

    @classmethod
    def from_records(cls, player: PlayerIdentity, records: Iterable[PullRecord]) -> PullHistory:
        """Build a history of supplied observations without inferring coverage."""
        rows = list(records)
        totals = PullTotals()
        dates = []
        for row in rows:
            if row.pulled_at is not None:
                dates.append(row.pulled_at)
            if not row.is_draw:
                totals.gifts += row.count
                continue
            if row.stream is not None:
                if row.stream.kind == "character":
                    totals.character_draws += row.count
                else:
                    totals.weapon_draws += row.count
            if row.is_free:
                totals.free_draws += row.count
            if row.rarity == 6:
                totals.six_star_draws += row.count
        return cls(
            player=player,
            records=rows,
            totals=totals,
            from_time=min(dates, default=None),
            to_time=max(dates, default=None),
        )

    def save(self, path: str | Path) -> None:
        """Save complete normalized history and checkpoints in versioned JSON."""
        data = {"version": _JSON_VERSION, "history": _public_data(self)}
        with _write_file(path) as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")

    @classmethod
    def load(cls, path: str | Path) -> PullHistory:
        """Load a history saved with save()."""
        with Path(path).open(encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != _JSON_VERSION:
            raise ValueError("unsupported pull-history JSON version")
        return cls.model_validate(data.get("history"))

    def to_csv(self, path: str | Path) -> None:
        """Export normalized record columns as UTF-8 CSV."""
        with _write_file(path) as file:
            writer = csv.DictWriter(file, fieldnames=_CSV_FIELDS)
            writer.writeheader()
            for row in self.records:
                columns = {name: getattr(row, name) for name in _CSV_FIELDS if name in type(row).model_fields}
                writer.writerow({
                    **columns,
                    "stream_kind": row.stream.kind if row.stream else None,
                    "stream_pool": row.stream.pool_id if row.stream else None,
                    "item_id": row.item.id,
                    "item_name": row.item.name,
                    "pulled_at": row.pulled_at.isoformat() if row.pulled_at else None,
                })

    @classmethod
    def from_csv(cls, path: str | Path, *, player: PlayerIdentity) -> PullHistory:
        """Load record observations for the given player, with unknown coverage."""
        rows = []
        identities: set[tuple[str, str]] = set()
        with Path(path).open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if tuple(reader.fieldnames or ()) != _CSV_FIELDS:
                raise ValueError("unexpected pull-history CSV columns")
            for fields in reader:
                if None in fields or None in fields.values():
                    raise ValueError(f"invalid pull-history CSV row {reader.line_num}")
                row = _csv_record(fields)
                if row.stream is not None and row.sequence_id:
                    identity = row.stream.key, row.sequence_id
                    if identity in identities:
                        raise ValueError(f"duplicate pull-history CSV sequence on row {reader.line_num}")
                    identities.add(identity)
                rows.append(row)
        return cls.from_records(player, rows)


def _csv_record(fields: dict[str, str]) -> PullRecord:
    stream_kind, stream_pool = fields.pop("stream_kind"), fields.pop("stream_pool")
    stream = PullStream.model_validate({"kind": stream_kind, "pool_id": stream_pool}) if (
        stream_kind or stream_pool
    ) else None
    item = ItemSummary.model_validate({
        "id": fields.pop("item_id"), "name": fields.pop("item_name"), "rarity": fields["rarity"] or None,
    })
    values: dict[str, Any] = dict(fields)
    for optional in ("pool_version", "rarity", "pulled_at", "is_free", "is_new", "pity_at_drop"):
        values[optional] = fields[optional] or None
    return PullRecord.model_validate({**values, "id": fields["sequence_id"], "stream": stream, "item": item})


def _public_data(value: Any) -> Any:
    """Serialize declared history fields only."""
    if isinstance(value, OutputModel):
        return {field: _public_data(getattr(value, field)) for field in type(value).model_fields}
    if isinstance(value, list):
        return [_public_data(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@contextmanager
def _write_file(path: str | Path) -> Iterator[IO[str]]:
    target = Path(path)
    file = NamedTemporaryFile(
        dir=target.parent, mode="w", encoding="utf-8", newline="", delete=False
    )
    temporary = Path(file.name)
    try:
        with file:
            yield file.file
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
