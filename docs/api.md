# Phase-one API guide

Fetch methods return the service's decoded data field without model conversion.
Lists and scalar values keep their original shape. No Enka player endpoint or
calculated statistic is used in this phase.

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

client.endfield.characters returns raw card records. showcase_only=True uses
configured showcase IDs/order. full=True fetches individual build endpoints.
client.endfield.character requires exactly one of char_id, name or index.
Names must be unique after NFKC/casefold normalization in the requested locale.
Indexes are nonnegative positions; numeric strings remain IDs or names. Direct
full-ID lookup avoids downloading a roster. Canonical IDs arrive with resolution.

Languages: en, ja, ko, zh-Hans, zh-Hant. Regional aliases normalize locally;
unsupported languages raise ConfigError. News/pulls use regional query codes.
Enka's fourteen asset languages are a separate future capability. Caller
language does not change credentials or session default headers.

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
ServerError, NetworkError and DecodeError. Errors retain safe status/code/path,
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
