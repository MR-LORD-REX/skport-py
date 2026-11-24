# Languages and configuration

Use `ClientConfig` for shared settings and method-level `lang` when a particular
response needs a different language. Per-call languages do not change the parent
client's defaults.

## Supported languages

- `en`: English. Aliases include `en-US` and `en-GB`.
- `ja`: Japanese. Aliases include `ja-JP` and `jp`.
- `ko`: Korean. Aliases include `ko-KR` and `kr`.
- `zh-Hans`: Simplified Chinese. Aliases include `zh-CN` and `chs`.
- `zh-Hant`: Traditional Chinese. Aliases include `zh-TW` and `cht`.

Language inputs are case-insensitive, and underscores normalize to hyphens.
Unsupported values raise `ConfigError`. The `Language` enum is also available
from `skport`.

```python
from skport import Language, SkportClient

async with SkportClient(tokens=tokens, lang=Language.EN) as client:
    english = await client.endfield.card(skport_id=skport_id)
    japanese = await client.endfield.card(skport_id=skport_id, lang="ja-JP")
```

Name-based character selection uses the requested response language. Canonical
asset localization is separate from the SKPORT languages the SDK supports.

## Create a configuration

```python
from pathlib import Path

from skport import ClientConfig, SkportClient

config = ClientConfig(
    lang="en",
    timeout=20.0,
    per_token_concurrency=1,
    max_attempts=3,
    assets_dir=Path(".skport-assets"),
    icon_source="skport",
)

async with SkportClient(tokens=tokens, config=config) as client:
    card = await client.endfield.card(skport_id=skport_id)
```

Only `region="global"` is supported. Selecting the CN deployment raises
`ConfigError`.

## Request settings

- `timeout=20.0`: HTTP request timeout in seconds.
- `per_token_concurrency=1`: maximum concurrent operations per authenticated account.
- `min_interval=0.0`: optional minimum pacing interval for an account.
- `cooldown=60.0`: public account cooldown policy after failures that require it.
- `max_attempts=3` and `retry_backoff=0.25`: safe-read retry policy.
- `refresh_interval=None`: optional proactive credential refresh policy in seconds.
  It is a caller-selected interval, not a documented upstream credential lifetime.

Different account tokens can handle requests concurrently. Reuse a client or API
so its credential pool and connections can be reused.

## Response and credential storage

`cache=True` enables the bounded in-memory response cache. `cache_size=512`
controls its entry limit. Raw signed GET helpers generally expose `ttl`; use
`ttl=0` to bypass response caching for that read. Verification methods always
bypass cached responses.

Intermediate login credentials remain in memory by default. `login_store=None`
disables persistence. Set `login_store=Path(...)` if your application wants an
opt-in credential store between runs, and keep that file in private application
storage.

## Asset settings

Use `calculate_stats`, `missing_assets`, `icon_source`, `assets_dir`,
`assets_ref`, `assets_offline`, and `assets_auto_update` to control enrichment.
See [assets and images](assets-and-images.md) for their defaults and update behavior.

## Share an API across languages

```python
from skport import SkportAPI, SkportClient

async with SkportAPI(tokens=tokens, lang="en") as api:
    async with SkportClient(api=api) as english_client:
        english = await english_client.endfield.verify_skid(skport_id)

    japanese_api = api.with_language("ja")
    async with SkportClient(api=japanese_api) as japanese_client:
        japanese = await japanese_client.endfield.verify_skid(skport_id)
```

The language view shares transport, credentials, and response caching with its
parent. Closing a borrowing client or view does not close the parent API.
Pass configuration when constructing the API; a borrowing `SkportClient(api=...)`
does not accept `tokens`, `config`, `lang`, or `region` at the same time.
