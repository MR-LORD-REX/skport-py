# Errors and retries

SDK failures derive from `SkportError`. Catch a specific exception when your
application can handle that condition, or catch `SkportError` at its integration
boundary.

## Handle a public lookup

```python
import asyncio
import os

from skport import PrivacyError, SkportClient, SkportError, TargetNotFound


async def main() -> None:
    async with SkportClient(tokens=[os.environ["SKPORT_TOKEN"]]) as client:
        try:
            card = await client.endfield.card(skport_id=os.environ["SKPORT_ID"])
        except PrivacyError:
            print("This player's requested information is private.")
        except TargetNotFound:
            print("No matching visible Endfield account was found.")
        except SkportError as error:
            print(type(error).__name__, error.status, error.path)
        else:
            print(card.player.name)


if __name__ == "__main__":
    asyncio.run(main())
```

## Choose the appropriate response

- `ConfigError`: correct invalid arguments, unsupported settings, or selectors.
- `AuthError`: the supplied account token or an authenticated session was rejected.
- `PoolExhausted`: the public credential pool has no healthy available account.
- `TargetNotFound`: check the target ID and role filters; default selection may be ambiguous.
- `PrivacyError` or `ForbiddenError`: handle source visibility or permission restrictions.
- `RateLimitError`: respect the upstream delay and reduce request volume if needed.
- `NetworkError` or `ServerError`: a request failed or the upstream service is unavailable.
- `DecodeError`: the service did not return the expected response structure.
- `AssetError`, `MappingError`, or `UnsupportedFormula`: canonical enrichment failed.
- `AlreadyCheckedIn`: the owner has already claimed the daily attendance reward.
- `APIError`: another unsuccessful business or HTTP response was received.

Errors expose request context such as `status`, `code`, `path`, `attempt`, and
`retry_after` when available. An absent field is `None`. Error classification
depends on the endpoint and response; do not treat one business code as a
universal authentication failure.

## Automatic retries

Safe reads retry transient network/server failures and rate-limit responses,
using the configured attempt limit and any supplied `Retry-After` delay.
Authenticated reads can refresh a rejected session before repeating the read.
Owner calls retain the supplied account identity during recovery.

Writes, including `check_in()`, are not automatically replayed after uncertain
network failures. Before retrying an owner write from your application, inspect
the relevant account state when the service provides a way to do so.

## Missing canonical data

By default, a failed build resolution or calculation returns a partial build
with `issues`, `stats=None`, and `calculation_state="unavailable"`. This is a
successful SKPORT fetch with incomplete enrichment, not a fabricated stat result.

Use `ClientConfig(missing_assets="raise")` to propagate enrichment errors.
An explicit `await client.update_assets()` raises `AssetError` on failure while
preserving the previous valid snapshot.

## Enable diagnostic logging

```python
from skport.logging import configure

configure(level="DEBUG")
```

Logging is opt-in and does not configure the root logger. SDK request logs contain
safe metadata rather than full payloads, tokens, or request headers. Your own
application should likewise avoid logging account tokens and raw login data.

See [configuration](languages-and-configuration.md) for timeout and retry settings.
