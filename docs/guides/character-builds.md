# Character builds

Character methods return `CharacterBuild` objects containing progression,
artwork, skills, talents, weapons, essence terms, equipment, and calculated
static stats when canonical data is available.

The examples below run inside an open `SkportClient` context.

## Select one character

Supply exactly one of `char_id`, `name`, or `index`:

```python
by_id = await client.endfield.character(
    skport_id=skport_id,
    char_id=character_id,
)

by_name = await client.endfield.character(
    skport_id=skport_id,
    name="Yvonne",
    lang="en",
)

by_index = await client.endfield.character(
    skport_id=skport_id,
    index=0,
)
```

- `char_id` is the opaque SKPORT character ID, available as
  `build.identity.skport_id`. It is not an Enka template ID.
- `name` matches the response language after Unicode normalization and
  case-insensitive comparison. It must identify one character.
- `index` is a nonnegative position in the returned list. With
  `showcase_only=True`, it uses the configured showcase order.

The default `full=True` requests the individual character endpoint. A normalized
direct ID lookup also reads the player's card to include their in-game name in
`build.owner`. With `raw=True`, a direct ID lookup skips that card read. Name,
index, and `full=False` lookups reuse the card already fetched for selection.
Use `full=False` to build from the character record returned in the card.

## Fetch a collection

```python
characters = await client.endfield.characters(skport_id=skport_id)

full_builds = await client.endfield.characters(
    skport_id=skport_id,
    showcase_only=True,
    full=True,
)
```

Collection requests use card records by default. `full=True` also requests the
individual character endpoint for each record. Both collection and single
requests accept `role_id`, `server_id`, and `lang`.

## Read the loadout

```python
print(by_id.name, by_id.level, by_id.potential)
print(by_id.element.key, by_id.profession.key)
print(by_id.images.splash.url)

if by_id.weapon is not None:
    print(by_id.weapon.name, by_id.weapon.level, by_id.weapon.base_attack)

for piece in by_id.equipment:
    print(piece.slot, piece.name, piece.defense)
    for line in piece.stat_lines:
        print(line.name, line.display, line.level)

for equipment_set in by_id.equipment_sets:
    print(equipment_set.name, equipment_set.pieces, equipment_set.active)
```

The equipment positions are `body`, `arms`, `accessory1`, and `accessory2`.
Unequipped positions are absent. A combined equipment stat line keeps each
affected property in `effects` and `stat_ids`.

`equipment_sets` includes observed sets below the activation threshold.
`set_effects` contains canonical static modifiers from active sets. Conditional
set descriptions remain display text; they are not applied as unconditional
sheet bonuses.

## Read stats safely

```python
if by_id.stats is not None:
    print(by_id.stats.hp, by_id.stats.attack, by_id.stats.defense)
    print(by_id.stats.percent("critical_rate"))
    for property_id, stat in by_id.stats.values.items():
        print(property_id, stat.name, stat.value, stat.unit, stat.display)
else:
    print(by_id.status, by_id.calculation_state)
    for issue in by_id.issues:
        print(issue.code, issue.message)
```

Fractional stats are stored as fractions: `0.05` means `5.0%`. Use the model's
display helpers rather than inferring units from a number's size. A fraction
may exceed `1.0`. See [output models](../reference/output-models.md).

The calculator produces a static sheet using canonical curves, potential,
weapon effects, equipment enhancements, unlocked attributes, active sets, and
supported unconditional passives. It does not simulate conditional combat
effects, team buffs, damage rotations, or tactical-item activation.

## Partial builds and raw data

Missing canonical data produces a renderable partial build by default. SKPORT
names and artwork remain available, while `stats` is `None` and unknown numeric
loadout values remain `None`. Configure `missing_assets="raise"` when successful
canonical resolution and the requested calculation are required.

To receive raw service data and skip asset resolution:

```python
raw_build = await client.endfield.character(
    skport_id=skport_id,
    char_id=character_id,
    raw=True,
)
```

See [assets and images](assets-and-images.md) for refresh and outage handling.
