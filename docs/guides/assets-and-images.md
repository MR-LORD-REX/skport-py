# Assets and images

Player information comes from SKPORT. Canonical identities and stat calculations
use a local snapshot of official Enka data. Image references retain SKPORT and
Enka alternatives where those URLs are available.

## Default behavior

- `icon_source="skport"` prefers SKPORT artwork.
- `calculate_stats=True` requests static calculated stats.
- `missing_assets="partial"` retains a partial build when canonical data is missing.
- `assets_auto_update=False` reuses a valid local snapshot without an update request.
- `assets_offline=False` permits the initial download and explicit updates.

Client construction and `warm()` do not download assets. The first typed build
request downloads a snapshot if no valid cache exists. Subsequent clients load
the saved snapshot by default.

## Update assets explicitly

Within an open main client:

```python
update = await client.update_assets()
print(update.changed, update.revision, update.previous_revision)
```

The update resolves the configured official source revision, validates a coherent
set of tables, and installs it atomically. `changed` is false when the source
commit matches the loaded snapshot.

Successful updates affect subsequent builds. Existing model objects retain the
data and `asset_revision` they were created with. A failed update raises
`AssetError` and retains the previous valid disk and memory snapshot.

## Use your own cache directory

```python
from pathlib import Path

from skport import ClientConfig, SkportClient

config = ClientConfig(assets_dir=Path(".skport-assets"))

async with SkportClient(tokens=tokens, config=config) as client:
    build = await client.endfield.character(skport_id=skport_id, index=0)
```

Without `assets_dir`, the SDK uses a writable user cache under `skport/enka`.
`assets_ref` defaults to `"master"`; supply a branch or complete commit to choose
the upstream source for downloads and updates.

## Continue during an Enka outage

If the snapshot already contains a character and its loadout, the SDK can return
that build and calculated stats while Enka is unavailable. Player requests still
use SKPORT, and artwork can use the retained SKPORT URLs.

To prohibit Enka asset requests:

```python
config = ClientConfig(
    assets_dir=Path(".skport-assets"),
    assets_offline=True,
    icon_source="skport",
)
```

Prepare a valid snapshot before enabling this setting. `assets_offline=True`
blocks canonical downloads and `update_assets()`; SKPORT requests continue.
New characters or equipment absent from that snapshot can return partial builds.
Image links alone do not establish their canonical stats.

`assets_auto_update=True` opts into an initial refresh when loading a cache and
a refresh attempt when resolution finds missing canonical data. Failed refreshes
retain usable cached data.

## Select an image source

```python
async with SkportClient(tokens=tokens, icon_source="enka") as client:
    build = await client.endfield.character(skport_id=skport_id, index=0)
    print(build.images.splash.url)
    print(build.images.splash.skport, build.images.splash.enka)
```

Each `ImageLinks` object exposes:

- `skport` and `enka`: available candidate URLs.
- `preferred`: configured source preference.
- `effective_source`: source selected from nonempty candidates, or `None`.
- `url`: selected URL, or `None`.

If the preferred candidate is absent, the model selects the available
alternative. This checks metadata presence, not HTTP availability. The SDK does
not download or probe bitmap images. An application can read a specific
candidate directly, download it, and apply its own image cache or fallback.

Portrait variants and some decorative icons may have only one known provider.
Canonical URLs are not fabricated for unresolved characters or items. Stable
element, profession, rarity, and stat keys let a renderer choose local icons
and colors.

## Require complete calculation data

```python
config = ClientConfig(missing_assets="raise")
```

This propagates canonical resolution or calculation errors instead of returning
a partial build. Use `calculate_stats=False` to skip arithmetic while retaining
available canonical metadata. See [character builds](character-builds.md) for
the calculation's static scope.
