# API guide

`SkportClient.endfield` returns normalized Pydantic player cards, character
builds and supported activity reports. Character builds include static
calculated stats when their canonical data is available. Player data comes
from SKPORT; calculations use a local Enka asset snapshot. No live Enka player
endpoint is called.

`SkportAPI` and `client.endfield.raw` return the service's decoded `data` field
without model conversion. Lists and scalar values keep their original shape.
Card and character methods accept `raw=True` to return the fetched wire data
and skip asset resolution/calculation.

## Construction and lifecycle

Create SkportAPI(tokens=[...]) once and reuse it. warm() authenticates public
units concurrently; ordinary reads authenticate lazily. SkportClient(api=api)
borrows it; SkportClient(tokens=[...]) creates and owns an API.

with_language(lang) returns a borrowing view sharing credentials, response cache,
pull-token cache and transport. Closing a view or borrowing facade keeps its
parent alive. Closing the owner drains operations and clears RAM credentials.
Injected pools/transports remain owned by their caller; Transport never closes
an injected aiohttp session.

ClientConfig exposes timeout, per_token_concurrency, cooldown, min_interval,
refresh_interval, cache_size, login_store, max_attempts and retry_backoff.
refresh_interval is a caller policy, not an asserted service TTL. Credentials
stay in memory by default; login_store enables opt-in persistence.
Only the global deployment is implemented; CN settings raise ConfigError.

Build settings include `icon_source`, `calculate_stats`, `missing_assets`,
`assets_dir`, `assets_ref`, `assets_offline` and `assets_auto_update`. See
[models and assets](models.md) for their defaults and behavior.

## Public and owner identities

cards, binding, user and web_user take either skport_id or token. Public lookups
can use any dummy account; own lookups require the explicit owner's token.
Omitting both or supplying both is an error.

Target(user_id, role_id, server_id) distinguishes social ID, game UID and server.
resolve_target(skport_id, role_id=..., server_id=...) always checks visible
bindings. Omit role_id to discover the game UID automatically. If supplied,
the UID and optional server must match a binding for that SKPORT ID; otherwise
TargetNotFound is raised before fetching game data. A unique default binding is
used when no UID is supplied; ambiguous accounts require explicit selection.

Owner calls validate the selected role against that token's bindings. A public
role cannot substitute. Owner tokens outside the public pool stay separate and
never enter public rotation.

## Multiple bound accounts

Public UID/server selection applies to other users too, provided the requested
role is returned by binding(skport_id=...). Supplying role_id/server_id can select
a non-default visible account or server. The dummy authentication token is the
viewer; it does not determine which target account is inspected.

Automatic selection respects app.defaultUid (or binding.isDefault), then the
chosen account's defaultRole. A default role inside a secondary account is not
the profile-wide default. Conflicting or absent defaults remain ambiguous.

Owner attendance, inventory and records can also select a non-default role using
role=Role(uid, server_id), but it must occur in binding(token=owner_token).
Those operations cannot use another person's public binding.

Public cross-account inspection is live-verified; the currently available
profile has one role, so actual non-default-account visibility remains unverified.
To check a multi-account profile when available, run:

~~~
python local/scripts/check_bindings.py --skport-id YOUR_SKPORT_ID
~~~

This read-only probe resolves the default and tests every visible UID/server
pair. It records role/default metadata and success/error results, never credentials,
full card data or daily actions.

## Endpoint groups

Shared API helpers:

- cards, binding: game cards and visible bindings.
- user, web_user: public or explicit-owner social profile.
- user_items: community feed with page_token/page_size.
- account_basic, third_party: publisher account data, explicit token required.
- resolve_target: Endfield target convenience method.

api.endfield helpers:

- detail(Target), character(Target, char_id=...): card and individual build.
- owned_card(token=...), owned_character(token=..., char_id=...): explicit owner data.
- crisis_contract(Target, contract_id=...), indie_hard(Target): public records.
- enums, wiki_catalog(type_sub_id=...), wiki_item(item_id): localized wiki/labels.
- char_banners, weapon_banners, news: banner and publisher bulletin metadata.
- attendance(token=...), check_in(token=...), inventory(token=...): owner data/actions.
- character_pulls(token=...), weapon_pools(token=...), weapon_pulls(token=..., pool_id=...): raw record pages.
- pulls.iter_character_pages(token=...): sequential pages with cursor guards.

Owner methods accept role= as a Role or owner header, validated against bindings.
Most signed GET methods expose lang and ttl; ttl=0 bypasses cached responses.
Successful writes invalidate that owner's cached reads.

## Characters and languages

`client.endfield.card(skport_id=...)` returns `PlayerCard` with ordered
`CharacterBuild` objects. The public list contains exposed characters and
does not imply the owner's complete roster. `source_scope` and
`roster_complete` keep that distinction explicit.

`client.endfield.characters(skport_id=...)` returns `list[CharacterBuild]`.
`showcase_only=True` uses configured showcase IDs/order. `full=True` fetches
individual build endpoints; the default uses the card's character records.
`client.endfield.character` requires exactly one of `char_id`, `name` or `index`.
Names must be unique after NFKC/casefold normalization in the requested locale.
Indexes are nonnegative positions; numeric strings remain IDs or names. Direct
ID lookup with `full=True` avoids downloading a roster. `char_id` selects an
opaque SKPORT character ID; canonical template and string IDs are output
metadata after resolution.

Owner methods stay bound to the explicitly supplied account token:

~~~py
from skport import Role

role = Role(game_uid, server_id)
card = await client.endfield.owned_card(token=owner_token, role=role)
roster = await client.endfield.owned_characters(
    token=owner_token, role=role, full=True
)
build = await client.endfield.owned_character(
    token=owner_token, role=role, name="Yvonne"
)
~~~

`owned_characters` uses the owner's returned roster without a public showcase
filter. `owned_character` accepts exactly one of `char_id`, `name` or `index`,
with `full=True` by default. Its optional `operator_id` is the owner endpoint's
additional query field; it does not replace the required character selector.
All three methods accept `lang` and `raw=True`. Roles are checked against the
owner token's bindings before game data is fetched.

Additional typed reports are `activity(skport_id=...)`, `factory(skport_id=...)`,
`monument(skport_id=...)` and `contract(skport_id=...)`. They accept public
`role_id`, `server_id` and `lang` selection. Wiki and pull-history endpoints
currently remain raw; their output model families are available for future
adapters.

Languages: en, ja, ko, zh-Hans, zh-Hant. Regional aliases normalize locally;
unsupported languages raise ConfigError. News/pulls use regional query codes.
Canonical Enka localization is stored separately from SKPORT's supported
request languages. Caller language does not change credentials or session
default headers.

## Asset loading and manual updates

`icon_source="skport"` is the default. Each `ImageLinks` retains available
SKPORT and Enka alternatives, with `.url` selecting the preferred available
candidate. This is URL selection; the SDK does not download or probe images.

The default `assets_auto_update=False` loads a valid local snapshot without
checking Enka. The first typed build request downloads canonical tables if no
valid cache exists and `assets_offline=False`. Construction and `warm()` do
not download assets.

`await client.update_assets()` explicitly installs the newest verified snapshot
from `assets_ref`. Its `AssetUpdate` result exposes `changed`,
`previous_revision` and `snapshot`. A failed update raises `AssetError` while
preserving the previous valid snapshot. Future builds use the newly installed
revision; previously returned models retain their original data.

Use `assets_offline=True` to prohibit Enka asset requests, including manual
updates. This setting still permits SKPORT API requests. Existing cached
character/loadout records can provide static calculations while Enka is down.
New characters or equipment missing from the snapshot produce partial builds,
or raise errors when `missing_assets="raise"`.

## Authentication, retries and diagnostics

Cold public login is grant plus credential exchange. cred/salt are reused; owner
discovery is lazy. An unambiguous auth failure on a safe read tries unsigned
salt refresh, then same-account full exchange if cred itself is rejected.
Auth-recovery replay is limited to one. Refresh network failures propagate
without discarding the credential or forcing full authentication.

GET/HEAD/OPTIONS retry transient failures and honor Retry-After. Writes never
auto-retry, including daily claims with uncertain outcomes. Business 10001 is
context-dependent; positive expiry/privacy signals precede missing-target mapping.

All errors derive from SkportError. Specific classes include AuthError,
TargetNotFound, ForbiddenError, PrivacyError, AlreadyCheckedIn, RateLimitError,
ServerError, NetworkError, DecodeError, AssetError, MappingError and
UnsupportedFormula. Errors retain safe status/code/path,
retry delay and attempt context.

skport.logging.configure(level="DEBUG") opts into safe request metadata.
Root logging is untouched; payloads/tokens are never logged. api.metrics retains
bounded signed-request measurements, rather than a full telemetry exporter.
TTLCache copies mutable data, bounds memory, protects every waiter from producer
cancellation and fences in-flight invalidation.

## Live validation limits

On 24 November 2026 the manual matrix passed 86 reads across five locales.
Eight exposed character IDs and numeric build values remained identical; names
translated in Japanese, Korean and both Chinese variants. The dummy provider
has no Endfield role: owner attendance/inventory/records have offline contract
tests, but their live owner success is not established. The script never claims
daily rewards.
