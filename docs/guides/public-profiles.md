# Public profiles

Use a target's SKPORT ID to inspect the Endfield data they expose. Your configured
account tokens authenticate requests as viewers; they do not determine which
public player is selected.

Your viewer token can come from a separate SKPORT account; it does not need an
Endfield binding. See [Account tokens](../getting-started/account-tokens.md) for
the official token endpoint and separate public/owner account setup.

The examples below run inside an open `SkportClient` context. See the
[quickstart](../getting-started/quickstart.md) for a complete script.

Before fetching a card, follow the illustrated [SKPORT ID and privacy guide](skport-id-and-privacy.md).
It shows where to copy the profile ID, how to enable global card visibility, and
how to make individual card sections public.

## Verify a SKPORT ID

```python
user = await client.endfield.verify_skid(skport_id)

print(user.skport_id)
print(user.skport_username)
print(user.game_uid, user.in_game_name)
print(user.server_id, user.server_name)
```

The result keeps the SKPORT username separate from the in-game name. Verification
uses fresh social-profile and binding reads and does not load character assets.
It raises an SDK exception when authentication fails, the profile is malformed,
or no suitable Endfield binding is available.

## Select the game account

Omit `role_id` to discover the default visible Endfield role. If a player has
multiple roles, select a particular UID and server explicitly:

```python
user = await client.endfield.verify_skid(
    skport_id,
    role_id=game_uid,
    server_id=server_id,
)

card = await client.endfield.profile(
    skport_id,
    role_id=user.game_uid,
    server_id=user.server_id,
)
```

The selected UID and server are checked against that target's visible bindings.
A supplied game UID cannot substitute for the SKPORT ID. If no unique default
can be selected, the client raises `TargetNotFound`; provide explicit filters.

## Read a player card

```python
card = await client.endfield.profile(skport_id)

print(card.player.name)
print(card.authority_level, card.world_level)
print(card.counts.characters, len(card.characters))
print(card.source_scope, card.roster_complete)
```

`profile()` is an alias for `card()`. Both return a `PlayerCard` with the
selected Endfield role. `counts.characters` is the reported ownership total.
`characters` is the list returned by the public endpoint. `roster_complete`
indicates whether those counts agree when the source provides an ownership
total. It can be `None` if the information is unavailable.

Read `showcase_ids` for the player's configured showcase IDs. To request only
those characters in configured order:

```python
showcase = await client.endfield.characters(
    skport_id=skport_id,
    showcase_only=True,
)
```

Public methods respect upstream visibility. A player's public card should not
be treated as a complete account inventory. For token-owner data, use
[owner methods](owner-accounts.md).

## Read the social profile

`skport_profile()` returns a `SocialProfile` for the target's SKPORT community
account. It reads the community profile without resolving an Endfield binding.

```python
social = await client.endfield.skport_profile(skport_id)
print(social.skport_username, social.biography)
print(social.avatar.url, social.counts.followers)
```

For the previous raw social response from `profile()`, call
`skport_profile(skport_id, raw=True)`.

## Activity and progression reports

```python
activity = await client.endfield.activity(skport_id=skport_id)
factory = await client.endfield.factory(skport_id=skport_id)
monument = await client.endfield.monument(skport_id=skport_id)
contract = await client.endfield.contract(skport_id=skport_id)
```

These methods return `LiveStatus`, `FactoryState`, `MonumentState`, and
`ContractState`. They accept the same public `role_id`, `server_id`, and `lang`
selection. Optional fields and empty collections represent information the
service did not supply. Resource counters may exceed their maximum; use the
reported values rather than assuming every progress ratio is at most one.

See the [Endfield reference](../reference/endfield.md) for method parameters.
