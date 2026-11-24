"""Locale-aware candidate indexes and explicit mapping failures."""

from __future__ import annotations

import json
import unicodedata
from collections import defaultdict
from typing import Any

from skport.errors import MappingError


def name_key(value: str) -> str:
    """Normalize a name without making localized text the canonical identity."""
    return unicodedata.normalize("NFKC", value).strip().casefold()


def name_index(records: dict[str, Any], localizations: dict[str, Any]) -> dict[str, set[str]]:
    """Keep every candidate when canonical names collide in any locale."""
    result: dict[str, set[str]] = defaultdict(set)
    for locale in localizations.values():
        for record_id, record in records.items():
            name = locale.get(str(record.get("NameHash")))
            if name:
                result[name_key(str(name))].add(str(record_id))
    return dict(result)


def choose(
    records: dict[str, Any],
    candidates: set[str],
    *,
    kind: str,
    revision: str,
    equivalent_fields: tuple[str, ...] = (),
) -> tuple[str, dict[str, Any], tuple[str, ...]]:
    """Require uniqueness, permitting documented equivalent calculation aliases."""
    selected = sorted(candidates, key=lambda key: (not key.isdigit(), int(key) if key.isdigit() else key))
    if len(selected) == 1:
        key = selected[0]
        return key, records[key], ()
    if selected and equivalent_fields:
        signatures = {
            json.dumps({field: records[key].get(field) for field in equivalent_fields}, sort_keys=True)
            for key in selected
        }
        if len(signatures) == 1:
            key = selected[0]
            warning = f"{kind} aliases {','.join(selected)} have equivalent calculation data; canonical {key} selected"
            return key, records[key], (warning,)
    raise MappingError(
        f"{kind} could not be resolved uniquely",
        context={"kind": kind, "candidates": selected, "asset_revision": revision},
    )
