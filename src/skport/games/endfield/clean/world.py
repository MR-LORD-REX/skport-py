"""Preserve factory and exploration information without card-layout transforms."""

from __future__ import annotations

from typing import Any

from skport.config import ImageSource
from skport.games.endfield.clean.common import image_links, numeric, timestamp
from skport.games.endfield.models import (
    AreaProgress,
    Cabin,
    CrewMember,
    FactoryState,
    ItemSummary,
    PlayerIdentity,
    RegionProgress,
    ResourceMeter,
    Settlement,
)

_EXPLORATION = {
    "puzzleCount": "Puzzles",
    "trchestCount": "Chests",
    "equipTrchestCount": "Equipment chests",
    "pieceCount": "Fragments",
    "blackboxCount": "Blackboxes",
    "trstarCount": "Aurylenes",
}


def build_regions(domains: list[dict[str, Any]], preferred: ImageSource) -> list[RegionProgress]:
    """Keep separate exploration categories, settlement meters and officer icons."""
    regions = []
    for domain in domains:
        money = domain.get("moneyMgr") or {}
        settlements = []
        for entry in domain.get("settlements") or []:
            settlements.append(
                Settlement(
                    id=str(entry.get("id") or ""),
                    name=str(entry.get("name") or ""),
                    level=int(numeric(entry.get("level"))),
                    experience=ResourceMeter(
                        key="settlement_experience",
                        name="Experience",
                        current=numeric(entry.get("exp")),
                        maximum=numeric(entry.get("expToLevelUp")),
                        note="maximum level" if entry.get("isFinalMaxLevel") else "",
                    ),
                    stock=ResourceMeter(
                        key="settlement_stock",
                        name="Stock",
                        current=numeric(entry.get("remainMoney")),
                        maximum=numeric(entry.get("moneyMax")),
                    ),
                    officer=ItemSummary(
                        id=str(entry.get("officerCharIds") or ""),
                        icon=image_links(entry.get("officerCharAvatar"), preferred=preferred),
                    )
                    if entry.get("officerCharAvatar") or entry.get("officerCharIds")
                    else None,
                    maximum_level=bool(entry.get("isFinalMaxLevel")),
                    last_tick_at=timestamp(entry.get("lastTickTime")),
                )
            )
        areas = []
        for entry in domain.get("levels") or []:
            counters = []
            for key, name in _EXPLORATION.items():
                count = entry.get(key)
                if isinstance(count, dict):
                    counters.append(
                        ResourceMeter(
                            key=key,
                            name=name,
                            current=numeric(count.get("count")),
                            maximum=numeric(count.get("total")),
                        )
                    )
            areas.append(
                AreaProgress(
                    id=str(entry.get("levelId") or ""),
                    name=str(entry.get("name") or ""),
                    counters=counters,
                )
            )
        regions.append(
            RegionProgress(
                id=str(domain.get("domainId") or ""),
                name=str(domain.get("name") or ""),
                level=int(numeric(domain.get("level"))),
                funds=ResourceMeter(
                    key="region_funds",
                    name="Funds",
                    current=numeric(money.get("count")),
                    maximum=numeric(money.get("total")),
                ),
                settlements=settlements,
                areas=areas,
                factory=domain.get("factory"),
            )
        )
    return regions


def build_factory_state(data: dict[str, Any], player: PlayerIdentity, preferred: ImageSource) -> FactoryState:
    """Normalize regional factory state and cabin crew from a player snapshot."""
    detail = data.get("detail", data)
    cabins = [
        Cabin(
            id=str(room.get("id") or ""),
            name=str(room.get("name") or ""),
            level=int(numeric(room.get("level"))),
            crew=[
                CrewMember(
                    id=str(member.get("charId") or ""),
                    name=str(member.get("name") or ""),
                    icon=image_links(member.get("avatarUrl"), preferred=preferred),
                    physical_strength=member.get("physicalStrength"),
                    favorability=member.get("favorability"),
                )
                for member in room.get("chars") or []
            ],
            kind=room.get("type"),
            reports=room.get("reports") or {},
        )
        for room in (detail.get("spaceShip") or {}).get("rooms") or []
    ]
    return FactoryState(
        player=player,
        regions=build_regions(detail.get("domain") or [], preferred),
        cabins=cabins,
        snapshot_at=timestamp((detail.get("base") or {}).get("saveTime")),
    )
