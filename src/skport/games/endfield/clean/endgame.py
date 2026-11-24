"""Normalize event stages and contract runs without losing team identity."""

from __future__ import annotations

from typing import Any

from skport.config import ImageSource
from skport.games.endfield.clean.common import description, image_links, numeric, rarity, semantic, timestamp
from skport.games.endfield.clean.profile import build_medal
from skport.games.endfield.models import (
    CharacterBuild,
    CharacterImages,
    ContractModifier,
    ContractState,
    CrisisContract,
    EnemySummary,
    EventStage,
    MonumentEvent,
    MonumentState,
    PlayerIdentity,
    ResourceMeter,
    StageRun,
    TeamMember,
)


def _team(
    entries: list[dict[str, Any]], preferred: ImageSource, roster: list[CharacterBuild] | None
) -> list[TeamMember]:
    """Join known build artwork by opaque ID while preserving unknown participants."""
    known = {build.identity.skport_id: build for build in roster or []}
    result = []
    for position, entry in enumerate(entries):
        character_id = str(entry.get("charId") or "")
        build = known.get(character_id)
        images = (
            build.images.model_copy(deep=True)
            if build
            else CharacterImages(
                avatar=image_links(entry.get("avatarUrl"), preferred=preferred),
                portrait=image_links(entry.get("avatarUrl"), preferred=preferred),
            )
        )
        if build and entry.get("avatarUrl"):
            images.avatar.skport = entry["avatarUrl"]
        result.append(
            TeamMember(
                character_id=character_id,
                template_id=build.identity.template_id if build else None,
                name=build.name if build else str(entry.get("name") or ""),
                level=int(numeric(entry.get("level")))
                if entry.get("level") is not None
                else build.level
                if build
                else None,
                rarity=rarity(entry.get("rarity"))
                if entry.get("rarity") is not None
                else build.rarity
                if build
                else None,
                potential=int(numeric(entry.get("potentialLevel")))
                if entry.get("potentialLevel") is not None
                else build.potential
                if build
                else None,
                position=position,
                element=build.element if build else semantic(entry.get("property"), preferred),
                profession=build.profession if build else semantic(entry.get("profession"), preferred),
                images=images,
                evolution=entry.get("evolvePhase"),
            )
        )
    return result


def _run(
    record: dict[str, Any] | None,
    preferred: ImageSource,
    roster: list[CharacterBuild] | None,
    completed: bool,
) -> StageRun | None:
    """Keep missing detailed records distinct from a stage's clear flag."""
    if not isinstance(record, dict):
        return None
    return StageRun(
        id=str(record.get("id") or ""),
        duration_seconds=numeric(record.get("passTs")) if record.get("passTs") is not None else None,
        completed_at=timestamp(record.get("ts")),
        completed=bool(record.get("isPass", completed)),
        score=int(numeric(record.get("indicatorCount")))
        if record.get("indicatorCount") is not None
        else None,
        waves=int(numeric(record.get("passWave"))) if record.get("passWave") is not None else None,
        is_best=bool(record.get("isBest")),
        team=_team(record.get("chars") or [], preferred, roster),
    )


def _enemy(entry: dict[str, Any], preferred: ImageSource) -> EnemySummary:
    """Retain enemy artwork and text without treating it as character equipment."""
    return EnemySummary(
        id=str(entry.get("id") or ""),
        name=str(entry.get("name") or ""),
        description=description(str(entry.get("desc") or "")),
        icon=image_links(entry.get("imageUrl"), preferred=preferred),
        level=entry.get("level"),
        ability=entry.get("ability"),
    )


def build_monument_report(
    data: dict[str, Any],
    player: PlayerIdentity,
    preferred: ImageSource,
    roster: list[CharacterBuild] | None = None,
) -> MonumentState:
    """Read summary or detailed monument payloads into event/stage models."""
    detail = data.get("detail", data)
    source = detail.get("indieHard") or detail
    events = []
    for group in source.get("indieHardGroups") or []:
        stages = []
        rules: list[str] = []
        for pair in group.get("dungeonGroups") or []:
            normal = pair.get("normalDungeon") or {}
            hard = pair.get("hardDungeon") or {}
            head = normal or hard
            for text in (head.get("desc"), head.get("feature")):
                if text:
                    formatted = description(str(text), head.get("featureParams"))
                    rules.extend(line.strip() for line in formatted.splitlines() if line.strip())
            stages.append(
                EventStage(
                    id=str(head.get("id") or ""),
                    name=str(head.get("name") or ""),
                    recommended_level=int(numeric(head.get("recommendLevel")))
                    if head.get("recommendLevel") is not None
                    else None,
                    enemies=[_enemy(enemy, preferred) for enemy in head.get("enemies") or []],
                    normal=_run(normal.get("bestRecord"), preferred, roster, bool(normal.get("isPass"))),
                    hard=_run(hard.get("bestRecord"), preferred, roster, bool(hard.get("isPass"))),
                    normal_cleared=bool(normal.get("isPass")),
                    hard_cleared=bool(hard.get("isPass")),
                    normal_id=normal.get("id"),
                    hard_id=hard.get("id"),
                )
            )
        events.append(
            MonumentEvent(
                id=str(group.get("id") or ""),
                name=str(group.get("name") or ""),
                poster=image_links(group.get("pic"), preferred=preferred),
                medal=build_medal(group["achieve"], preferred) if group.get("achieve") else None,
                rules=list(dict.fromkeys(rules)),
                starts_at=timestamp(group.get("activityStartTs")),
                ends_at=timestamp(group.get("activityEndTs")),
                is_active=bool(group.get("isInActivity")),
                stages=stages,
            )
        )
    return MonumentState(
        player=player,
        events=events,
        snapshot_at=timestamp((detail.get("base") or {}).get("saveTime")),
    )


def _contract(
    status: dict[str, Any],
    source: dict[str, Any],
    preferred: ImageSource,
    roster: list[CharacterBuild] | None,
) -> CrisisContract:
    """Retain contract summary counters and detailed runs when the source has them."""
    names = {
        "weeklyMission": "Weekly missions",
        "indicatorMission": "Indicators",
        "stageMission": "Stage missions",
    }
    missions = [
        ResourceMeter(
            key=key,
            name=name,
            current=numeric(status[key].get("count")),
            maximum=numeric(status[key].get("total")),
        )
        for key, name in names.items()
        if isinstance(status.get(key), dict)
    ]
    dungeon = source.get("dungeon") or {}
    return CrisisContract(
        id=str(status.get("id") or ""),
        name=str(status.get("name") or ""),
        poster=image_links(status.get("headerImage") or status.get("kvImage"), preferred=preferred),
        medal=build_medal(status["achieve"], preferred) if status.get("achieve") else None,
        best_score=int(numeric(status.get("highest"))),
        attempts=int(numeric(status.get("challengeCount"))),
        missions=missions,
        starts_at=timestamp(status.get("startAtTs")),
        ends_at=timestamp(status.get("gameplayEndAtTs")),
        runs=[
            run
            for record in (source.get("history") or {}).get("records") or []
            if (run := _run(record, preferred, roster, bool(record.get("isPass")))) is not None
        ],
        modifiers=[
            ContractModifier(
                id=str(entry.get("id") or ""),
                name=str(entry.get("name") or ""),
                description=description(str(entry.get("desc") or ""), entry.get("descParams")),
                icon=image_links(entry.get("icon"), preferred=preferred),
                score=int(numeric(entry.get("score"))),
                is_unlocked=bool(entry.get("isUnlock")),
                params=entry.get("descParams") or {},
            )
            for entry in source.get("indicators") or []
        ],
        enemies=[_enemy(entry, preferred) for entry in dungeon.get("enemies") or []],
        ends_at_collection=timestamp(status.get("endAtTs")),
        rules=description(str(dungeon.get("desc") or "")),
    )


def build_contract_report(
    data: dict[str, Any],
    player: PlayerIdentity,
    preferred: ImageSource,
    roster: list[CharacterBuild] | None = None,
) -> ContractState:
    """Accept card summary lists or the separate detailed contract response."""
    detail = data.get("detail", data)
    payload = detail.get("crisisContract")
    if isinstance(payload, list):
        contracts = [_contract(status, {}, preferred, roster) for status in payload]
    elif isinstance(payload, dict):
        contracts = [_contract(payload.get("status") or payload, payload, preferred, roster)]
    else:
        contracts = []
    return ContractState(
        player=player,
        current=contracts[0] if contracts else None,
        contracts=contracts,
        snapshot_at=timestamp((detail.get("base") or {}).get("saveTime")),
    )
