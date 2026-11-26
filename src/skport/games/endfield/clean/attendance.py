"""Normalize daily attendance and check-in data."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from skport.config import ImageSource
from skport.errors import DecodeError
from skport.games.endfield.clean.common import image_links, numeric, timestamp, wire_list, wire_object
from skport.games.endfield.models.attendance import (
    AttendanceAwardRef,
    AttendanceDay,
    AttendanceReward,
    AttendanceStatus,
    CheckInResult,
)


def _rewards(value: Any, preferred: ImageSource) -> dict[str, AttendanceReward]:
    rewards = {}
    for award_id, raw in wire_object(value, "attendance resources").items():
        reward = wire_object(raw, "attendance resource")
        rewards[award_id] = AttendanceReward(
            id=reward.get("id") or award_id,
            name=reward.get("name") or "",
            count=reward["count"],
            icon=image_links(reward.get("icon"), preferred=preferred),
        )
    return rewards


def _days(data: Any) -> list[AttendanceDay]:
    return [
        AttendanceDay(award_id=row["awardId"], available=row["available"], done=row["done"])
        for row in (wire_object(value, "attendance day") for value in wire_list(data, "attendance calendar"))
    ]


def attendance_status(data: Any, preferred: ImageSource) -> AttendanceStatus:
    """Decode the owner's calendar and keep the service flag independent of its days."""
    raw = wire_object(data, "attendance")
    try:
        return AttendanceStatus(
            current_at=timestamp(raw.get("currentTs")),
            calendar=_days(raw["calendar"]),
            first=_days(raw.get("first", [])),
            rewards_by_id=_rewards(raw.get("resourceInfoMap", {}), preferred),
            has_today=raw["hasToday"],
        )
    except (KeyError, ValidationError) as exc:
        raise DecodeError("invalid attendance fields") from exc


def _awards(data: Any) -> list[AttendanceAwardRef]:
    return [AttendanceAwardRef.model_validate(row) for row in wire_list(data, "check-in award references")]


def check_in_result(data: Any, preferred: ImageSource) -> CheckInResult:
    """Decode ordered award references and available reward metadata."""
    raw = wire_object(data, "check-in")
    try:
        stamp = raw.get("ts")
        return CheckInResult(
            claimed_at=timestamp(stamp, milliseconds=numeric(stamp) >= 100_000_000_000),
            awards=_awards(raw["awardIds"]),
            tomorrow_awards=_awards(raw.get("tomorrowAwardIds", [])),
            rewards_by_id=_rewards(raw.get("resourceInfoMap", {}), preferred),
        )
    except (KeyError, ValidationError) as exc:
        raise DecodeError("invalid check-in fields") from exc
