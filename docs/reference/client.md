# Main client reference

`SkportClient` is the public facade for game data, reusable authentication, and
canonical assets. Import it and common configuration types from `skport`.

```python
from skport import ClientConfig, ImageSource, Language, SkportAPI, SkportClient
```

## Constructor

```text
SkportClient(
    api=None,
    *,
    tokens=None,
    config=None,
    lang=None,
    region=None,
    icon_source=None,
    assets=None,
)
```

Choose one API ownership mode:

- `tokens`: a nonempty list of account-token strings. The client creates and owns
  its `SkportAPI`; optional `config`, `lang`, and `region` apply to that API.
- `api`: an existing `SkportAPI` to borrow. Do not also pass `tokens`, `config`,
  `lang`, or `region`. The creator of the API remains responsible for closing it.

`icon_source` overrides the facade's image preference without changing a borrowed
API's configuration. It accepts `"skport"`, `"enka"`, or `ImageSource`.
`assets` can supply an existing `AssetManager`; the supplied manager remains
owned by its caller.

Construction performs no network requests.

## Context manager and close

```python
async with SkportClient(tokens=tokens) as client:
    card = await client.endfield.card(skport_id=skport_id)
```

`await client.close()` releases game resources and resources created by the
facade. Repeated calls are harmless. A supplied API or asset manager is not
closed by the borrowing facade. Using the facade after close raises `ConfigError`.

## endfield

`client.endfield` returns the cached `EndfieldClient` over the shared API and
asset manager. See the [Endfield reference](endfield.md).

## api

`client.api` exposes the underlying `SkportAPI`. Use its raw social and account
helpers or `client.endfield.raw` when you need decoded service data.

Raw methods preserve the original `data` field. Their return type may be an
object, list, or other service value; they do not calculate stats or construct
Pydantic output models.

## warm()

```python
await client.warm()
```

Authenticate the configured public token pool before application requests.
Ordinary reads authenticate lazily, so this step is optional. Warming does not
download canonical assets or claim attendance rewards.

## update_assets()

```python
update = await client.update_assets()
```

Return `AssetUpdate` after loading or updating official canonical tables. It exposes:

- `snapshot`: installed `AssetSnapshot`, including `revision` and `fetched_at`.
- `revision`: convenience property for the snapshot revision.
- `changed`: whether the installed source commit changed.
- `previous_revision`: prior revision, or `None` before the first installation.

Failure raises `AssetError` and retains a valid prior snapshot.
`assets_offline=True` disables this operation. See
[assets and images](../guides/assets-and-images.md).

## Shared API pattern

```python
async with SkportAPI(tokens=tokens, lang="en") as api:
    await api.warm()
    async with SkportClient(api=api) as first:
        user = await first.endfield.verify_skid(skport_id)
    async with SkportClient(api=api, icon_source="enka") as second:
        build = await second.endfield.character(skport_id=user.skport_id, index=0)
```

Both facades borrow the same transport, credential pool, and raw response cache.
Their asset managers are separate unless you pass the same manager through
`assets=`. API language views created with `api.with_language(...)` also borrow
the same API resources.

See [languages and configuration](../guides/languages-and-configuration.md)
for settings and language views.
