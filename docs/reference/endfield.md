# Endfield client reference

Access the Endfield client through `client.endfield`. Unless stated otherwise,
methods are asynchronous and return normalized Pydantic output models.

Public player methods take `skport_id` as a positional or keyword argument.
Owner methods take the account's `token` the same way. Use keywords for
options such as `role_id`, `server_id`, `role`, `lang`, and `raw`.

## Verification

### verify_skid

```text
await client.endfield.verify_skid(
    skport_id,
    *,
    role_id=None,
    server_id=None,
    lang=None,
)
```

Return `VerifiedUser` for a public SKPORT profile and selected visible Endfield
binding. The SKPORT ID can be a nonempty string or integer. The method bypasses
cached responses and does not load cards or assets.

### verify_token

```text
await client.endfield.verify_token(token, *, role=None, lang=None)
```

Return `VerifiedUser` for the explicit token owner. The selected role must belong
to that token. The method uses fresh social and binding reads; its output does
not contain credentials. Missing or ambiguous Endfield bindings raise
`TargetNotFound`.

## Public player reads

### resolve

```text
await client.endfield.resolve(skport_id, *, role_id=None, server_id=None, lang=None)
```

Return `Target` with `user_id`, `role_id`, and `server_id`. Explicit role filters
are validated against the target's visible bindings.

### skport_profile

```text
await client.endfield.skport_profile(skport_id, *, lang=None, raw=False)
```

Return `SocialProfile` with the SKPORT username, biography, avatar, and
available community counts. Pass `raw=True` to get the decoded social response
previously returned by `profile()`.

### profile and card

```text
await client.endfield.profile(
    skport_id, *, role_id=None, server_id=None, lang=None, raw=False,
)
await client.endfield.card(
    skport_id, *, role_id=None, server_id=None, lang=None, raw=False,
)
```

`profile()` and `card()` return the same `PlayerCard`. With `raw=True`, either
method returns the decoded Endfield card response and skips asset resolution and
calculation.

### characters

```text
await client.endfield.characters(
    skport_id, *, role_id=None, server_id=None,
    showcase_only=False, full=False, lang=None, raw=False,
)
```

Return `list[CharacterBuild]`, or raw character records with `raw=True`.
`showcase_only` filters to configured showcase order. `full=True` fetches the
individual character endpoint for each selected record.

### character

```text
await client.endfield.character(
    skport_id, *, char_id=None, name=None, index=None,
    role_id=None, server_id=None, showcase_only=False,
    full=True, lang=None, raw=False,
)
```

Return one `CharacterBuild`, or a raw record with `raw=True`. Supply exactly one
of `char_id`, `name`, or `index`. Normalized direct ID lookup with `full=True`
also reads the player's card for the owner's in-game name; `raw=True` skips
that card request. Names use the requested response language and must match
uniquely. See [character builds](../guides/character-builds.md).

## Reports

```text
await client.endfield.activity(skport_id, *, role_id=None, server_id=None, lang=None)
await client.endfield.factory(skport_id, *, role_id=None, server_id=None, lang=None)
await client.endfield.monument(skport_id, *, role_id=None, server_id=None, lang=None)
await client.endfield.contract(skport_id, *, role_id=None, server_id=None, lang=None)
```

Return `LiveStatus`, `FactoryState`, `MonumentState`, and `ContractState`,
respectively. These report methods do not expose a `raw` switch; use their raw
endpoint helpers if your application needs service data directly.

## Owner reads

```text
await client.endfield.owned_card(token, *, role=None, lang=None, raw=False)

await client.endfield.owned_characters(
    token, *, role=None, full=False, lang=None, raw=False,
)

await client.endfield.owned_character(
    token, *, char_id=None, name=None, index=None,
    operator_id=None, role=None, full=True, lang=None, raw=False,
)

await client.endfield.owned_activity(token, *, role=None, lang=None)
```

Return `PlayerCard`, `list[CharacterBuild]`, and `CharacterBuild`, respectively.
`raw=True` skips normalization. Owner roster reads use returned records rather
than the public showcase filter. Single owner reads require exactly one of
`char_id`, `name`, or `index`.

Normalized single owner reads include the in-game name in `build.owner`. Direct
ID lookup also reads the owner's card for that identity; `raw=True` skips this
additional card read. Other selectors reuse the snapshot fetched for selection.

`role` accepts `Role(game_uid, server_id)` or the owner header string
`"3_<game_uid>_<server_id>"`. A role outside the token's bindings is rejected.

`owned_activity()` returns `LiveStatus` from the authenticated owner's card,
including source resource values and recovery/refresh timestamps. It does not
require public card sharing or load character assets. Like the public report
methods, it has no `raw` switch; use `raw.owned_card()` for the source snapshot.

## Attendance and inventory

```text
await client.endfield.attendance(token, *, role=None, lang=None, raw=True)
await client.endfield.inventory(token, *, role=None, lang=None, raw=True, enrich=False)
await client.endfield.check_in(token, *, role=None, lang=None, raw=True)
```

Pass `raw=False` to receive `AttendanceStatus`, `Inventory`, and
`CheckInResult` respectively. The default `raw=True` returns decoded service
data. `check_in()` sends one claim attempt and raises `AlreadyCheckedIn` for
a recognized duplicate claim. Inventory accepts `enrich=True` with `raw=False`
to fill available names and icons.

## Pull history

```text
await client.endfield.pulls(token, *, role=None, lang=None, since=None, after=None, featured_items=None)
```

Returns `PullHistory` scoped to the selected owner. Use `since` to extend a
previous history or `after` for an exclusive date cutoff. [Pull history guide](../guides/pull-history.md)

## Game reference

```text
await client.endfield.wiki_catalog(*, type_sub_id=..., type_main_id=1, lang=None)
await client.endfield.wiki_item(item_id, *, lang=None, index=None)
await client.endfield.char_banners(*, lang=None)
await client.endfield.weapon_banners(*, lang=None)
await client.endfield.news(*, lang=None)
await client.endfield.enums(*, lang=None)
```

The first two methods return `list[WikiSummary]` and `WikiPage`. Banner
methods return `list[Banner]`. `news()` returns a list of `Notice` records,
and `enums()` returns an `EnumCatalog`. [Wiki and banners guide](../guides/wiki.md)

## Raw endpoint access

`client.endfield.raw` exposes `EndfieldRawAPI`. Its helpers return decoded
service `data` and generally accept `lang` and, for signed reads, `ttl`.

- Public game helpers: `detail(target)`, `character(target, char_id=...)`,
  `indie_hard(target)`, and `crisis_contract(target, contract_id=...)`.
- Owner game helpers: `owned_card(token=...)`, `owned_character(token=..., char_id=...)`,
  `role_for(token, role=...)`, `attendance`, `inventory`, and `check_in`.
- Catalog and metadata helpers: `enums()`, `wiki_catalog(type_sub_id=...)`,
  `wiki_item(item_id)`, `char_banners()`, `weapon_banners()`, and `news()`.
- Pull helpers: `character_pulls(token=...)`, `weapon_pools(token=...)`, and
  `weapon_pulls(token=..., pool_id=...)`.
- Pagination: `raw.pulls.iter_character_pages(token=...)` yields raw pages
  sequentially and validates continuation cursors.

Use `ttl=0` on supported raw signed GET methods to bypass response caching.
