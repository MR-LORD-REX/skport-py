# skport-py

An async SKPORT SDK for inspecting public Endfield profiles with reusable account credentials. Requires Python 3.11 or newer.

`SkportClient` returns Pydantic player cards and character builds with static
calculated stats. SKPORT supplies player data and default artwork URLs; a local
Enka asset snapshot supplies canonical identities, curves and modifiers. The
SDK does not call Enka's live player API. `SkportAPI` remains available for raw
responses.

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
        print(character.images.splash.url)
        if character.stats is not None:
            print(character.stats.hp, character.stats.attack)
~~~

Each public account has a request semaphore; default concurrency is one. Credentials are retained in RAM and refreshed before falling back to a full exchange. Borrowing clients and language views do not close the shared API.

The game UID is discovered from the SKPORT ID. Supply role_id=game_uid to select
and validate a specific UID; a mismatch raises TargetNotFound. server_id is also
optional and checked against bindings when provided.

For convenient ownership, use SkportClient(tokens=[...]). Owner roster, single
character, attendance, inventory and pull methods require token= for that
account, even when it is outside the public pool:

~~~py
roster = await client.endfield.owned_characters(token=owner_token, full=True)
build = await client.endfield.owned_character(token=owner_token, index=0)
~~~

Verify a public SKPORT ID or the explicit token owner without loading assets:

~~~py
public_user = await client.endfield.verify_skid(skport_id)
owner = await client.endfield.verify_token(owner_token)
print(owner.skport_username, owner.game_uid, owner.in_game_name)
~~~

Languages: en, ja, ko, zh-Hans and zh-Hant. Regional aliases such as ja-JP and zh-TW are normalized. API.with_language(...) shares credentials, transport and cache without changing its parent.

## Assets and update gaps

Artwork retains both `skport` and `enka` URLs where each is available. The
default `icon_source="skport"` selects SKPORT URLs; `icon_source="enka"` prefers
the alternative while preserving both candidates. Renderers can choose directly
from those fields or read the selected `.url`.

Assets are loaded from the user cache first. `assets_auto_update=False` is the
default, so a valid snapshot does not require an Enka request when a client
starts. If no snapshot exists, the first typed build request downloads one
unless `assets_offline=True`. Use the main client method to refresh explicitly:

~~~py
update = await client.update_assets()
print(update.changed, update.snapshot.revision)
~~~

A failed update raises `AssetError` and retains the previous valid snapshot.
Existing characters can still produce builds and calculated stats during Enka
outages when their character and loadout data are in that snapshot, using
SKPORT artwork. `assets_offline=True` disables Enka asset requests only;
SKPORT player requests continue normally.

Missing canonical data returns a partial build by default, with `stats=None`,
`calculation_state="unavailable"` and diagnostic `issues`. Set
`ClientConfig(missing_assets="raise")` to require successful resolution and
calculation. See the [model guide](docs/models.md) for fields, units, asset
settings and calculation scope.

## Raw endpoints and errors

Use api.cards/binding/user/web_user for public social data; api.endfield for raw game endpoints. Social own-account lookups require token= instead of skport_id=. Results preserve the original data field, including lists and percentage values.

Typed card/character methods also accept `raw=True` to skip model conversion.
All errors derive from SkportError. Request logs are opt-in through
skport.logging.configure and contain safe endpoint metadata. See the
[API guide](docs/api.md) for endpoints, selectors and ownership.

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
