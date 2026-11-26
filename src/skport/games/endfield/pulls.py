"""Account-bound pull-history credentials, pages and incremental sync."""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from collections.abc import AsyncIterator, Collection, Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from skport.api.endpoints import GRANT
from skport.config import Language, parse_language, service_language
from skport.errors import AuthError, ConfigError, DecodeError, TargetNotFound
from skport.games.endfield import endpoints as ep
from skport.games.endfield.clean.common import timestamp
from skport.games.endfield.identity import Role
from skport.games.endfield.models.base import ModelIssue
from skport.games.endfield.models.identity import PlayerIdentity
from skport.games.endfield.models.item import ItemSummary
from skport.games.endfield.models.pulls import (
    BannerPity,
    PullCheckpoint,
    PullHistory,
    PullPage,
    PullPool,
    PullRecord,
    PullStream,
)

if TYPE_CHECKING:
    from skport.games.endfield.api import EndfieldRawAPI

_CHARACTER_PREFIX = "E_CharacterGachaPoolType_"
_CHARACTER_POOLS = ("Special", "Standard", "Beginner", "Joint", "Rerun")
_LIMITED = frozenset({"Special", "Joint", "Rerun"})
_BannerKey = tuple[str, str, int | None]


class PullHistoryAPI:
    """Keep record credentials in RAM and serialize all account-bound requests."""

    def __init__(self, endfield: EndfieldRawAPI) -> None:
        self.endfield = endfield
        self.api = endfield.api
        self._tokens: dict[tuple[str, str, str], tuple[float, str]] = self.api._credential_cache

    async def _record_token(self, token: str, owner: Role, language: Language) -> str:
        """Reuse a record token or exchange an account grant for the owner's game token."""
        key = self._key(token, owner)
        cached = self._tokens.get(key)
        if cached is not None and cached[0] > time.monotonic():
            return cached[1]
        grant = await self.api.external_request(
            "POST",
            self.api.config.hosts.account + GRANT,
            payload={"token": token, "appCode": self.api.config.protocol.gacha_app_code, "type": 1},
            headers={"x-language": language.value},
            lang=language,
        )
        if not isinstance(grant, dict) or not grant.get("token"):
            raise DecodeError("pull-history grant did not contain an account access token")
        access_token = grant["token"]
        bindings = await self.api.external_request(
            "GET",
            self.api.config.hosts.binding + ep.PULL_BINDING,
            params={"token": access_token, "appCode": "endfield"},
            lang=language,
        )
        if not isinstance(bindings, dict):
            raise DecodeError("pull-history binding response must be an object")
        matching = {
            str(binding["uid"])
            for app in bindings.get("list") or []
            if app.get("appCode") == "endfield"
            for binding in app.get("bindingList") or []
            if binding.get("uid")
            and any(
                str(item.get("roleId")) == owner.role_id and str(item.get("serverId")) == owner.server_id
                for item in binding.get("roles") or []
            )
        }
        if len(matching) != 1:
            raise TargetNotFound("the selected owner role has no unique pull-history account binding")
        result = await self.api.external_request(
            "POST",
            self.api.config.hosts.binding + ep.PULL_TOKEN,
            payload={"uid": matching.pop(), "token": access_token},
            lang=language,
        )
        if not isinstance(result, dict) or not result.get("token"):
            raise DecodeError("pull-history binding did not contain a game record token")
        record_token = str(result["token"])
        self._tokens[key] = (time.monotonic() + 600, record_token)
        return record_token

    async def _page(
        self,
        path: str,
        *,
        token: str,
        role: Role | str | None,
        lang: str | Language | None,
        parameters: dict[str, str],
    ) -> Any:
        """Read one page within an owner lease, renewing rejected record tokens once."""
        language = parse_language(lang or self.api.config.lang)
        owner = await self.endfield.role_for(token, role=role, lang=language)
        return await self._owned_page(path, token=token, owner=owner, language=language, parameters=parameters)

    async def _owned_page(
        self, path: str, *, token: str, owner: Role, language: Language, parameters: dict[str, str]
    ) -> Any:
        async with self.api.pool.lease(token=token):
            for attempt in range(2):
                record_token = await self._record_token(token, owner, language)
                try:
                    return await self.api.external_request(
                        "GET",
                        self.api.config.hosts.webview + path,
                        params={
                            "lang": service_language(language),
                            "token": record_token,
                            "server_id": owner.server_id,
                            **parameters,
                        },
                        lang=language,
                    )
                except AuthError:
                    self._tokens.pop(self._key(token, owner), None)
                    if attempt:
                        raise
        raise AssertionError("unreachable pull-history request state")

    @staticmethod
    def _key(token: str, owner: Role) -> tuple[str, str, str]:
        """Keep credential caches separate for each account, role, and server."""
        return (hashlib.sha256(token.encode()).hexdigest(), owner.role_id, owner.server_id)

    def clear(self) -> None:
        """Drop retained pull-history tokens when the owning API closes."""
        self._tokens.clear()

    async def character_pulls(
        self,
        *,
        token: str,
        pool_type: str = "E_CharacterGachaPoolType_Special",
        seq_id: str = "",
        role: Role | str | None = None,
        lang: str | Language | None = None,
    ) -> Any:
        """Fetch one character record page for the supplied owner's banner."""
        parameters = {"pool_type": pool_type}
        if seq_id:
            parameters["seq_id"] = seq_id
        return await self._page(ep.CHAR_PULLS, token=token, role=role, lang=lang, parameters=parameters)

    async def weapon_pools(
        self,
        *,
        token: str,
        role: Role | str | None = None,
        lang: str | Language | None = None,
    ) -> Any:
        """Fetch the owner's raw weapon pool list."""
        return await self._page(ep.WEAPON_POOLS, token=token, role=role, lang=lang, parameters={})

    async def weapon_pulls(
        self,
        *,
        token: str,
        pool_id: str,
        seq_id: str = "",
        role: Role | str | None = None,
        lang: str | Language | None = None,
    ) -> Any:
        """Fetch one weapon record page for the supplied owner's pool."""
        if not pool_id:
            raise ConfigError("pool_id must not be empty")
        parameters = {"pool_id": pool_id}
        if seq_id:
            parameters["seq_id"] = seq_id
        return await self._page(ep.WEAPON_PULLS, token=token, role=role, lang=lang, parameters=parameters)

    async def iter_character_pages(self, *, token: str, **kwargs: Any) -> AsyncIterator[Any]:
        """Yield raw pages and reject a repeated or absent continuation cursor."""
        cursor = ""
        seen: set[str] = set()
        while True:
            page = await self.character_pulls(token=token, seq_id=cursor, **kwargs)
            yield page
            if not page.get("hasMore"):
                return
            rows = page.get("list") or []
            next_cursor = str(rows[-1].get("seqId") or "") if rows else ""
            if not next_cursor or next_cursor in seen:
                raise DecodeError("pull-history continuation cursor is missing or repeated")
            seen.add(next_cursor)
            cursor = next_cursor

    async def history(
        self,
        *,
        token: str,
        role: Role | str | None = None,
        lang: str | Language | None = None,
        since: PullHistory | None = None,
        after: datetime | None = None,
        featured_items: Mapping[_BannerKey, Collection[str]] | None = None,
    ) -> PullHistory:
        """Fetch visible owner records or resume a saved history by stream."""
        if after is not None:
            if since is not None:
                raise ConfigError("choose either a saved pull history or an after timestamp")
            if after.utcoffset() is None:
                raise ConfigError("after must be a timezone-aware datetime")
            after = after.astimezone(UTC)
        language = parse_language(lang or self.api.config.lang)
        owner = await self.endfield.role_for(token, role=role, lang=language)
        credential = await self.api.pool.credential_for(token)
        player = PlayerIdentity(
            skport_id=credential.user_id, game_uid=owner.role_id, server_id=owner.server_id, name=owner.nickname
        )
        if since is not None and _owner_identity(since.player) != _owner_identity(player):
            raise ConfigError("saved pull history belongs to a different SKPORT account or Endfield role")

        pools = _parse_pools(await self._owned_page(
            ep.WEAPON_POOLS, token=token, owner=owner, language=language, parameters={}
        ))
        streams = [
            PullStream(kind="character", pool_id=_CHARACTER_PREFIX + pool) for pool in _CHARACTER_POOLS
        ]
        streams.extend(PullStream(kind="weapon", pool_id=pool.id) for pool in pools)
        records: dict[tuple[str, str], PullRecord] = {}
        checkpoints: dict[str, PullCheckpoint] = {}
        if since is not None:
            for row in since.records:
                records[_record_id(row)] = row.model_copy(deep=True)
            checkpoints = {checkpoint.stream.key: checkpoint.model_copy(deep=True) for checkpoint in since.checkpoints}
        issues = {(issue.code, issue.path): issue.model_copy(deep=True) for issue in since.issues} if since else {}
        issues["pull_history_window", ""] = ModelIssue(
            code="pull_history_window", message="SKPORT only returns records within its available history window."
        )
        for stream in streams:
            previous = checkpoints.get(stream.key)
            if previous is not None and (stream.key, previous.sequence_id or "") not in records:
                previous = None
            rows, checkpoint, overlap = await self._sync_stream(
                stream, token=token, owner=owner, language=language, previous=previous, after=after
            )
            if previous is not None and not overlap:
                issues["pull_history_gap", stream.key] = ModelIssue(
                    code="pull_history_gap",
                    path=stream.key,
                    message="The previous sequence is outside the available records. The history can contain a gap.",
                )
            records.update((_record_id(row), row) for row in rows)
            checkpoints[stream.key] = checkpoint

        history = PullHistory.from_records(player, sorted(records.values(), key=_record_order, reverse=True))
        previous_pools = {pool.id: pool.model_copy(deep=True) for pool in since.pools} if since else {}
        previous_pools.update((pool.id, pool) for pool in pools)
        history.pools = list(previous_pools.values())
        history.checkpoints = list(checkpoints.values())
        verified: dict[_BannerKey, Collection[str]] = (
            {
                (counter.stream.key, counter.banner_id, counter.pool_version): counter.featured_item_ids
                for counter in since.pity
                if counter.stream is not None and counter.featured_item_ids
            }
            if since is not None else {}
        )
        verified.update(featured_items or {})
        gaps = {path for code, path in issues if code == "pull_history_gap"}
        history.pity = _summarize_pity(history.records, checkpoints, verified, gaps)
        history.issues = list(issues.values())
        return history

    async def _sync_stream(
        self,
        stream: PullStream,
        *,
        token: str,
        owner: Role,
        language: Language,
        previous: PullCheckpoint | None,
        after: datetime | None,
    ) -> tuple[list[PullRecord], PullCheckpoint, bool]:
        if stream.kind == "character":
            path, parameters = ep.CHAR_PULLS, {"pool_type": stream.pool_id}
        else:
            path, parameters = ep.WEAPON_PULLS, {"pool_id": stream.pool_id}
        rows: list[PullRecord] = []
        seen_cursors: set[str] = set()
        previous_date: datetime | None = None
        checkpoint = PullCheckpoint(stream=stream)
        while True:
            page = _parse_page(await self._owned_page(
                path, token=token, owner=owner, language=language, parameters=parameters
            ), stream)
            for row in page.records:
                if previous is not None and row.sequence_id == previous.sequence_id:
                    checkpoint.sequence_id = checkpoint.sequence_id or previous.sequence_id
                    checkpoint.covered_from = previous.covered_from
                    checkpoint.reached_end = previous.reached_end
                    return rows, checkpoint, True
                if row.pulled_at is None:
                    raise DecodeError("pull-history row is missing its timestamp")
                if previous_date is not None and row.pulled_at > previous_date:
                    raise DecodeError("pull-history pages are not ordered by descending timestamp")
                previous_date = row.pulled_at
                if after is not None and row.pulled_at <= after:
                    return rows, checkpoint, False
                if checkpoint.sequence_id is None:
                    checkpoint.sequence_id = row.sequence_id
                checkpoint.covered_from = row.pulled_at
                rows.append(row)
            if not page.has_more:
                checkpoint.reached_end = True
                return rows, checkpoint, False
            cursor = page.next_cursor
            if cursor is None or cursor in seen_cursors:
                raise DecodeError("pull-history continuation cursor is missing or repeated")
            seen_cursors.add(cursor)
            parameters["seq_id"] = cursor


def _owner_identity(player: PlayerIdentity) -> tuple[str, str | None, str | None]:
    return player.skport_id, player.game_uid, player.server_id


def _identifier(value: Any) -> str:
    return str(value).strip() if type(value) in (int, str) else ""


def _parse_pools(data: Any) -> list[PullPool]:
    items = data.get("list") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise DecodeError("weapon pull pools must be a list")
    pools: dict[str, PullPool] = {}
    for item in items:
        if not isinstance(item, dict) or not (pool_id := _identifier(item.get("poolId"))):
            raise DecodeError("weapon pull pool is missing a pool ID")
        try:
            pools[pool_id] = PullPool(
                id=pool_id,
                name=str(item.get("poolName") or ""),
                pool_type=_identifier(item.get("poolType")) or None,
                online=item.get("online"),
            )
        except ValidationError as exc:
            raise DecodeError("weapon pull pool metadata is malformed") from exc
    return list(pools.values())


def _parse_page(data: Any, stream: PullStream) -> PullPage:
    if not isinstance(data, dict) or not isinstance(data.get("list"), list):
        raise DecodeError("pull-history page must contain a list")
    has_more = data.get("hasMore")
    if not isinstance(has_more, bool):
        raise DecodeError("pull-history page is missing its continuation flag")
    try:
        rows = [_parse_row(row, stream) for row in data["list"]]
    except ValidationError as exc:
        raise DecodeError("pull-history row metadata is malformed") from exc
    return PullPage(records=rows, has_more=has_more, next_cursor=rows[-1].sequence_id if has_more and rows else None)


def _parse_row(row: Any, stream: PullStream) -> PullRecord:
    if not isinstance(row, dict) or not (sequence_id := _identifier(row.get("seqId"))):
        raise DecodeError("pull-history row is missing a sequence ID")
    character = stream.kind == "character"
    item_id = _identifier(row.get("charId" if character else "weaponId"))
    kind = str(row.get("kind") or ("draw" if item_id else "unknown"))
    if kind == "draw" and not item_id:
        raise DecodeError("pull-history draw is missing an item ID")
    return PullRecord(
        id=sequence_id,
        sequence_id=sequence_id,
        kind=kind,
        stream=stream,
        item=ItemSummary(
            id=item_id,
            name=str((row.get("charName" if character else "weaponName")) or row.get("nameText") or ""),
            rarity=row.get("rarity"),
        ),
        banner_id=_identifier(row.get("poolId")) or (stream.pool_id if not character else ""),
        banner_name=str(row.get("poolName") or ""),
        pool_version=row.get("poolVersion"),
        rarity=row.get("rarity"),
        pulled_at=timestamp(row.get("gachaTs"), milliseconds=True),
        is_draw=kind == "draw",
        is_free=row.get("isFree", None if character else False),
        is_new=row.get("isNew"),
    )


def _record_id(row: PullRecord) -> tuple[str, str]:
    if row.stream is None or not row.sequence_id:
        raise ConfigError("saved pull records must have stream and sequence identities")
    return row.stream.key, row.sequence_id


def _record_order(row: PullRecord) -> tuple[datetime, int, str, str]:
    sequence = row.sequence_id.lstrip("0") if row.sequence_id.isascii() and row.sequence_id.isdecimal() else ""
    return (
        row.pulled_at or datetime.min.replace(tzinfo=UTC),
        len(sequence),
        sequence or row.sequence_id,
        row.stream.key if row.stream else "",
    )


def _policy(stream: PullStream) -> tuple[str, int | None, int | None, int | None]:
    """Return the hard-pity scope, hard limit, featured limit and selector limit."""
    if stream.kind == "weapon":
        return stream.key, 40, 80, None
    pool_type = stream.pool_id.removeprefix(_CHARACTER_PREFIX)
    if pool_type in _LIMITED:
        return "character:limited", 80, 120, None
    if pool_type == "Standard":
        return stream.key, 80, None, 300
    if pool_type == "Beginner":
        return stream.key, 50, None, None
    return stream.key, None, None, None


def _hard_progress(
    rows: list[PullRecord], checkpoints: list[PullCheckpoint], hard_limit: int, gaps: set[str]
) -> tuple[int, int | None]:
    observed = 0
    uncertain = False
    for row in rows:
        if row.is_free is True:
            continue
        if row.is_free is None:
            uncertain = True
            continue
        if row.rarity == 6:
            anchor = row.pulled_at
            tied = any(
                other.pulled_at == anchor and other.stream != row.stream and other.is_free is not True
                for other in rows
            )
            covered = (
                anchor is not None
                and any(checkpoint.stream == row.stream for checkpoint in checkpoints)
                and all(
                    (checkpoint.covered_from is not None and checkpoint.covered_from <= anchor)
                    or (
                        checkpoint.reached_end and checkpoint.stream != row.stream
                        and checkpoint.stream.key not in gaps
                    )
                    for checkpoint in checkpoints
                )
            )
            current = observed if covered and not uncertain and not tied and observed < hard_limit else None
            return observed, current
        if row.rarity is None:
            uncertain = True
        observed += row.count
    return observed, None


def _summarize_pity(
    records: list[PullRecord],
    checkpoints: dict[str, PullCheckpoint],
    featured_items: Mapping[_BannerKey, Collection[str]],
    gaps: set[str],
) -> list[BannerPity]:
    scopes: dict[str, list[PullRecord]] = defaultdict(list)
    coverage: dict[str, list[PullCheckpoint]] = defaultdict(list)
    counters: dict[_BannerKey, BannerPity] = {}
    for checkpoint in checkpoints.values():
        coverage[_policy(checkpoint.stream)[0]].append(checkpoint)
    for row in records:
        if not row.is_draw or row.stream is None:
            continue
        scope, limit, featured, selector = _policy(row.stream)
        scopes[scope].append(row)
        banner_id = row.banner_id or row.stream.pool_id
        key = (row.stream.key, banner_id, row.pool_version)
        if key not in counters:
            verified = featured_items.get(key, ()) if featured is not None else ()
            counters[key] = BannerPity(
                stream=row.stream,
                banner_id=banner_id,
                name=row.banner_name,
                pool_version=row.pool_version,
                hard_scope=scope,
                hard_limit=limit,
                featured_guarantee=featured,
                featured_item_ids=[verified] if isinstance(verified, str) else sorted(set(verified)),
                selector_limit=selector,
            )
        if row.is_free is False:
            counter = counters[key]
            counter.total += row.count
            if row.rarity == 6 and row.item.id in counter.featured_item_ids:
                counter.featured_received = True
    progress: dict[str, tuple[int, int | None]] = {}
    for counter in counters.values():
        hard_scope = counter.hard_scope
        if hard_scope is None or counter.hard_limit is None:
            continue
        if hard_scope not in progress:
            progress[hard_scope] = _hard_progress(scopes[hard_scope], coverage[hard_scope], counter.hard_limit, gaps)
        counter.observed_since_six_star, counter.current = progress[hard_scope]
    return list(counters.values())
