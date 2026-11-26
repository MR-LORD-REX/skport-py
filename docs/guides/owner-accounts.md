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

Normalized direct ID lookup also reads the owner's card so that `build.owner`
includes the in-game name. `raw=True` keeps the direct character request without
that additional card read. Name, index, and `full=False` lookups reuse their
selection snapshot.

Card and character owner methods accept `lang` and `raw=True`. Typed owner
builds use the same local assets and stat pipeline as public builds.

## Live resources

```python
activity = await client.endfield.owned_activity(token=owner_token, role=role)
print(activity.sanity.current, activity.sanity.maximum)
print(activity.sanity.recovery_at)
```

`owned_activity()` returns normalized `LiveStatus` using the same resource
normalizer as public activity reads. It preserves the captured server clock,
overflow values, and source recovery or refresh timestamps. Missing resource
sections are `None`. The request uses the token owner's authenticated card and
does not require public card sharing or character asset loading.

## Inventory and attendance

```python
inventory = await client.endfield.inventory(token=owner_token, role=role, raw=False)
attendance = await client.endfield.attendance(token=owner_token, role=role, raw=False)
print(len(inventory.operators), len(attendance.available_days))
```

Use `raw=False` for typed results. The default `raw=True` returns the decoded
service response. To claim the account's daily attendance reward, call
`check_in()` explicitly.

```python
result = await client.endfield.check_in(token=owner_token, role=role, raw=False)
for award, reward in zip(result.awards, result.rewards, strict=True):
    print(reward.name if reward else award.id)
```

`check_in()` sends one write attempt. An explicit already-claimed response
raises `AlreadyCheckedIn`.

## Pull records

Fetch typed history for the selected owner and save its checkpoints for a
later refresh.

```python
history = await client.endfield.pulls(token=owner_token, role=role)
for record in history.records:
    print(record.pulled_at, record.item.name)
```

For incremental sync, pity, and export formats, see the
[pull history guide](pull-history.md).

See [errors and retries](errors-and-retries.md) for failure handling.
