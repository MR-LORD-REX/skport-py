# Quickstart

This example verifies a public player, fetches their Endfield card, and prints
the exposed characters and any calculated stats.

Complete [installation](installation.md) first and set `SKPORT_TOKEN` and
`SKPORT_ID`. Save the following script as `quickstart.py`:

```python
import asyncio
import os

from skport import SkportClient


async def main() -> None:
    async with SkportClient(tokens=[os.environ["SKPORT_TOKEN"]]) as client:
        user = await client.endfield.verify_skid(os.environ["SKPORT_ID"])
        print(user.skport_username, user.game_uid, user.in_game_name)

        card = await client.endfield.card(skport_id=user.skport_id)
        print(card.player.name, card.authority_level, card.world_level)

        for build in card.characters:
            print(build.name, build.level, build.images.splash.url)
            if build.stats is not None:
                print(build.stats.hp, build.stats.attack, build.stats.defense)
            else:
                print(build.calculation_state, [issue.code for issue in build.issues])


if __name__ == "__main__":
    asyncio.run(main())
```

Run it:

```bash
python quickstart.py
```

The context manager closes resources created by the client. Authentication is
lazy: constructing the client performs no requests. Call `await client.warm()`
if you want to authenticate the configured public token pool before your first
application request.

## What to expect

Verification returns a `VerifiedUser` and performs fresh SKPORT profile and
binding reads. It does not load Enka assets. The game UID is selected from the
target's visible bindings; you do not need to know it in advance.

`card()` returns a `PlayerCard` containing normalized `CharacterBuild` objects.
The first build request downloads official canonical tables if no valid local
asset snapshot exists. Later clients reuse the snapshot by default. SKPORT
image URLs are preferred wherever available.

Some builds can be partial when their character or loadout is absent from the
local canonical data. Check `build.stats` before reading statistics. See
[assets and images](../guides/assets-and-images.md) for update and offline options.

## Fetch one character

Within the open client context:

```python
build = await client.endfield.character(
    skport_id=user.skport_id,
    index=0,
)
print(build.name, build.identity.skport_id)
```

Use exactly one selector: `char_id`, `name`, or `index`. An index refers to the
returned public list. It is not an Enka template ID.

## Export a response

```python
payload = card.model_dump(mode="json")
json_text = card.model_dump_json(indent=2)
```

Continue with [public profiles](../guides/public-profiles.md),
[character builds](../guides/character-builds.md), or
[owner accounts](../guides/owner-accounts.md).
