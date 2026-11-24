# Owner accounts

Owner methods operate on the account identified by the token supplied to that
method. They do not select an arbitrary viewer from the public token pool.

Follow [Account tokens](../getting-started/account-tokens.md) to sign in with your
game account and retrieve its token from the official SKPORT website. You can
keep public card sharing disabled when using token-bound methods for your own
account. Use a separate viewer token for public lookups if desired.

An owner token can be outside `SkportClient(tokens=[...])`. The SDK retains it
for owner requests without adding it to public rotation. The examples below
run inside an open client context.

## Verify the token owner

```python
owner = await client.endfield.verify_token(owner_token)
print(owner.skport_id, owner.skport_username)
print(owner.game_uid, owner.in_game_name, owner.server_id)
```

Verification uses fresh SKPORT binding and social-profile reads. The result
contains public identity information, not the token or intermediate credentials.
The account must have a suitable Endfield binding.

## Select a bound role

When the owner has multiple Endfield roles, supply a `Role`:

```python
from skport import Role

role = Role(game_uid, server_id)
owner = await client.endfield.verify_token(owner_token, role=role)
```

Owner methods also accept a role header string such as `"3_<game_uid>_<server_id>"`.
Every supplied role is checked against that token's bindings. Another player's
public UID cannot be used as the owner role.

## Fetch the owner's card and roster

```python
card = await client.endfield.owned_card(token=owner_token, role=role)

roster = await client.endfield.owned_characters(
    token=owner_token,
    role=role,
    full=True,
)

build = await client.endfield.owned_character(
    token=owner_token,
    role=role,
    index=0,
)
```

The returned card has `source_scope="owner"`. Roster selection uses the owner's
returned records, without applying the public showcase filter. The SDK still
reports the source's actual response; it does not manufacture missing records.

`owned_character()` accepts exactly one of `char_id`, `name`, or `index`.
Its default `full=True` reads the individual owner character endpoint.
`full=False` uses the owner's card record. The optional `operator_id` supplies
the endpoint's additional operator query field; it does not replace the selector.

Card and character owner methods accept `lang` and `raw=True`. Typed owner
builds use the same local assets and stat pipeline as public builds.

## Inventory and attendance

```python
inventory = await client.endfield.inventory(token=owner_token, role=role)
attendance = await client.endfield.attendance(token=owner_token, role=role)
```

These methods return raw decoded data. To claim the account's daily attendance
reward, call `check_in()` explicitly:

```python
result = await client.endfield.check_in(token=owner_token, role=role)
```

`check_in()` performs a write. The SDK does not automatically replay writes after
an uncertain network failure. An explicit already-claimed response raises
`AlreadyCheckedIn`.

## Pull records

Pull methods currently return raw pages through `client.endfield.raw`:

```python
page = await client.endfield.raw.character_pulls(
    token=owner_token,
    role=role,
)

async for page in client.endfield.raw.pulls.iter_character_pages(
    token=owner_token,
    role=role,
):
    for record in page.get("list", []):
        print(record)
```

The iterator follows pages sequentially and raises `DecodeError` for a missing
or repeated continuation cursor. Weapon history uses `weapon_pools()` followed
by `weapon_pulls(token=..., pool_id=...)`. Typed history and pity aggregation
are not exposed yet.

See [errors and retries](errors-and-retries.md) for failure handling.
