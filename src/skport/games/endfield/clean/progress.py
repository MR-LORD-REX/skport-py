"""Normalize live resources without advancing the captured snapshot clock."""

from __future__ import annotations

from typing import Any

from skport.config import ImageSource
from skport.games.endfield.clean.common import numeric, timestamp
from skport.games.endfield.models import LiveStatus, PlayerIdentity, ResourceMeter


def build_live_status(data: dict[str, Any], player: PlayerIdentity, preferred: ImageSource) -> LiveStatus:
    """Expose actual overflow and source-provided refresh/recovery timestamps."""
    detail = data.get("detail", data)
    stamina = detail.get("dungeon") or {}
    daily = detail.get("dailyMission") or {}
    weekly = detail.get("weeklyMission") or {}
    battle_pass = detail.get("bpSystem") or {}
    credits = detail.get("credit") or {}
    return LiveStatus(
        player=player,
        server_time=timestamp(detail.get("currentTs")),
        sanity=ResourceMeter(
            key="sanity",
            name="Sanity",
            current=numeric(stamina.get("curStamina")),
            maximum=numeric(stamina.get("maxStamina")),
            recovery_at=timestamp(stamina.get("maxTs")),
        )
        if "dungeon" in detail
        else None,
        daily=ResourceMeter(
            key="daily_activity",
            name="Daily activity",
            current=numeric(daily.get("dailyActivation")),
            maximum=numeric(daily.get("maxDailyActivation")),
        )
        if "dailyMission" in detail
        else None,
        weekly=ResourceMeter(
            key="weekly_routine",
            name="Weekly routine",
            current=numeric(weekly.get("score")),
            maximum=numeric(weekly.get("total")),
        )
        if "weeklyMission" in detail
        else None,
        battle_pass=ResourceMeter(
            key="battle_pass",
            name="Battle pass",
            current=numeric(battle_pass.get("curLevel")),
            maximum=numeric(battle_pass.get("maxLevel")),
        )
        if "bpSystem" in detail
        else None,
        credits=ResourceMeter(
            key="credits",
            name="Credits",
            current=numeric(credits.get("count")),
            maximum=numeric(credits.get("total")),
            refresh_at=timestamp(credits.get("nextRefreshTs")),
            note="claimed today" if credits.get("hasToday") else "",
        )
        if "credit" in detail
        else None,
        current_event={
            "war_echoes": detail.get("warEchoes") or {},
            "crisis_contract": detail.get("crisisContract") or [],
        },
        preferred_image_source=preferred,
    )
