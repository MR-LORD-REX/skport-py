# skport-py

An async SKPORT SDK for inspecting public Endfield profiles with reusable account credentials. Requires Python 3.11 or newer.

Phase one returns raw SKPORT data. Official Enka assets, canonical Pydantic builds and stat calculation are planned separately.

## Install for development

~~~
python -m pip install -e ".[dev]"
~~~

## Reuse one API

~~~
from skport import SkportAPI, SkportClient

async with SkportAPI(tokens=[token_a, token_b, token_c], lang="en") as api:
    await api.warm()
    async with SkportClient(api=api) as client:
        card = await client.endfield.card(
            skport_id=skport_id, lang="ja"
        )
        character = await client.endfield.character(
            skport_id=skport_id, index=0, lang="ja"
        )
~~~

Each public account has a request semaphore; default concurrency is one. Credentials are retained in RAM and refreshed before falling back to a full exchange. Borrowing clients and language views do not close the shared API.

The game UID is discovered from the SKPORT ID. Supply role_id=game_uid to select
and validate a specific UID; a mismatch raises TargetNotFound. server_id is also
optional and checked against bindings when provided.

For convenient ownership, use SkportClient(tokens=[...]). Owner attendance, inventory and pull methods require token= for that account, even when it is outside the public pool.

Languages: en, ja, ko, zh-Hans and zh-Hant. Regional aliases such as ja-JP and zh-TW are normalized. API.with_language(...) shares credentials, transport and cache without changing its parent.

## Raw endpoints and errors

Use api.cards/binding/user/web_user for public social data; api.endfield for raw game endpoints. Social own-account lookups require token= instead of skport_id=. Results preserve the original data field, including lists and percentage values.

All errors derive from SkportError. Request logs are opt-in through skport.logging.configure and contain safe endpoint metadata. See [API guide](docs/api.md) for endpoints, selectors and ownership.

## Validation

~~~
python -m pytest -q
python -m ruff check src local/tests local/scripts examples
python -m mypy src/skport
~~~

Default tests never use external services. For an explicit read-only live matrix, configure SKPORT_LIVE_TOKEN or use the authorized local capture, then run:

~~~
python local/scripts/live_matrix.py
~~~

The live matrix stores sanitized results under local/reports and never performs daily claims. The current dummy account can inspect other public profiles but has no Endfield binding, so owner-only live success remains unverified.

Design documents: [analysis.md](local/docs/analysis.md), [plan.md](local/docs/plan.md). The local working area is intentionally excluded from Git and distribution artifacts. Existing project license: GPL-3.0-only.
