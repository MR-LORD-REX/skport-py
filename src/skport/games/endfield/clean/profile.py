"""Convert SKPORT player snapshots into template-independent profile models."""

from __future__ import annotations

from typing import Any

from skport.config import ImageSource
from skport.errors import DecodeError
from skport.games.endfield.clean.common import image_links, numeric, timestamp
from skport.games.endfield.clean.world import build_regions
from skport.games.endfield.identity import Target
from skport.games.endfield.models import (
    CharacterBuild,
    MedalSummary,
    OwnershipCounts,
    PlayerCard,
    PlayerIdentity,
    ProfilePrivacy,
)


def build_medal(data: dict[str, Any], preferred: ImageSource, slot: int | None = None) -> MedalSummary:
    """Preserve medal progression and choose the observed display icon."""
    definition = data.get("achievementData") or data
    level = int(numeric(data.get("level")))
    plated = bool(data.get("isPlated"))
    initial = definition.get("initIcon") or definition.get("icon")
    selected = (
        definition.get("platedIcon")
        if plated
        else definition.get(f"reforge{level}Icon")
        if level > 1
        else initial
    ) or initial
    return MedalSummary(
        id=str(definition.get("id") or ""),
        name=str(definition.get("name") or ""),
        icon=image_links(selected, preferred=preferred),
        initial_icon=image_links(initial, preferred=preferred),
        plated_icon=image_links(definition.get("platedIcon"), preferred=preferred),
        level=level,
        plated=plated,
        slot=slot,
        obtained_at=timestamp(data.get("obtainTs")),
        category=definition.get("cate"),
    )


def build_player_card(
    data: dict[str, Any],
    characters: list[CharacterBuild],
    target: Target,
    locale: str,
    preferred: ImageSource,
    social: dict[str, Any] | None = None,
    privacy: dict[str, Any] | None = None,
) -> PlayerCard:
    """Normalize a game snapshot while retaining ownership and showcase ordering."""
    detail = data.get("detail", data)
    base = detail.get("base")
    if not isinstance(base, dict):
        raise DecodeError("player card detail must contain a base object")
    user = ((social or {}).get("user") or {}).get("basicUser") or {}
    player = PlayerIdentity(
        skport_id=target.user_id,
        game_uid=target.role_id,
        server_id=target.server_id,
        name=str(base.get("name") or user.get("nickname") or ""),
    )
    achievement = detail.get("achieve") or {}
    entries = {
        str((entry.get("achievementData") or {}).get("id") or ""): entry
        for entry in achievement.get("achieveMedals") or []
    }
    display = achievement.get("display") or {}
    medals = []
    if isinstance(display, dict):
        for position, medal_id in sorted(display.items(), key=lambda item: int(item[0])):
            entry = entries.get(str(medal_id))
            if entry is not None:
                medals.append(build_medal(entry, preferred, int(position)))
    flags = privacy or {}
    config = detail.get("config") or {}
    mission = base.get("mainMission") or {}
    revisions = {character.asset_revision for character in characters if character.asset_revision}
    return PlayerCard(
        player=player,
        avatar=image_links(base.get("avatarUrl") or user.get("avatar"), preferred=preferred),
        banner=image_links(user.get("backgroundImage"), preferred=preferred),
        biography=str(user.get("profile") or ""),
        mission=str(mission.get("description") or "") if isinstance(mission, dict) else str(mission),
        authority_level=int(numeric(base.get("level"))),
        world_level=int(numeric(base.get("worldLevel"))),
        experience=int(numeric(base.get("exp"))),
        counts=OwnershipCounts(
            characters=int(numeric(base.get("charNum"))),
            weapons=int(numeric(base.get("weaponNum"))),
            documents=int(numeric(base.get("docNum"))),
            achievements=int(numeric(achievement.get("count"))),
        ),
        created_at=timestamp(base.get("createTime")),
        snapshot_at=timestamp(base.get("saveTime")),
        server_time=timestamp(detail.get("currentTs")),
        medals=medals,
        characters=characters,
        showcase_ids=[str(value) for value in config.get("charIds") or []],
        privacy=ProfilePrivacy(
            card_visible=flags.get("cardOn"),
            details_visible=flags.get("detailOn"),
            character_visible=config.get("charSwitch"),
        ),
        regions=build_regions(detail.get("domain") or [], preferred),
        asset_revision=next(iter(revisions)) if len(revisions) == 1 else None,
        locale=locale,
        server_name=base.get("serverName"),
        last_login_at=timestamp(base.get("lastLoginTime")),
        modules=config.get("modules") or [],
        visibility=flags,
        roster_complete=len(characters) == int(numeric(base.get("charNum")))
        if base.get("charNum") is not None
        else None,
    )
