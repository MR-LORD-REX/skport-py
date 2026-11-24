# Output models

Normalized responses use Pydantic 2 models with snake_case fields. Import them
from `skport.games.endfield.models` or their focused modules.

```python
from skport.games.endfield.models import CharacterBuild, PlayerCard, VerifiedUser
```

## Serialization

```python
data = build.model_dump(mode="json")
text = build.model_dump_json(indent=2)
```

JSON serialization converts enums and timestamps to JSON-compatible values.
Property-map keys become strings in JSON objects. Unknown output metadata can
remain present; your application should read known fields without assuming a
response will contain only those fields.

## VerifiedUser

Verification returns:

- `skport_id`: social profile ID.
- `skport_username`: SKPORT social nickname.
- `game_uid`: selected Endfield role UID.
- `in_game_name`: nickname from the game binding; empty if omitted by the service.
- `server_id` and `server_name`: selected server information.
- `source_scope`: `"public"` or `"owner"`.

These fields contain no account token or intermediate login credentials.

## PlayerCard

Use `player` for the social ID, game UID, server ID, and in-game name. Other
fields include avatar/banner references, authority/world levels, experience,
ownership `counts`, mission text, source timestamps, medals, regions, and the
returned character builds.

`showcase_ids` records configured character IDs. `source_scope` distinguishes
public and owner reads. `roster_complete` compares returned characters with the
reported ownership count when available. Visibility information is retained in
`privacy`; a missing flag is not assumed to be true.

`asset_revision`, when available, identifies the canonical snapshot used for
the card's builds. Optional fields can be `None`, and some social fields remain
empty when they were not included in the fetched game snapshot.

## CharacterBuild

Core character information includes:

- `identity`: opaque SKPORT ID plus optional canonical `template_id` and `str_id`.
  Display-variant identities are separate when applicable.
- `name`, `level`, `max_level`, `evolution`, `potential`, and `rarity`.
- `element`, `profession`, and `weapon_type`: stable classification keys,
  localized names, and optional icon references.
- `images`: separate avatar, portrait, half-body, and splash variants.
- `weapon`, `equipment`, `equipment_sets`, `set_effects`, `skills`, `talents`,
  and optional `tactical_item`.
- `stats`, `status`, `calculation_state`, `asset_revision`, `locale`, and `issues`.

`status` is `"complete"` when canonical resolution and the requested calculation
succeed; otherwise it is `"partial"`. `calculation_state` is `"calculated"`,
`"unavailable"`, or `"not_requested"`.

When canonical data is unavailable, `stats` and unknown numeric loadout fields
remain `None`. Available SKPORT metadata is retained. A missing stat block is
not equivalent to a complete block of zero-valued stats.

## StatBlock and units

`StatBlock.values` maps property IDs to `StatValue` objects. Each value contains
`id`, `value`, `unit`, `name`, an optional icon, and `is_main`/`is_sub` flags.
The block exposes common numeric helpers such as `hp`, `attack`, `defense`,
`strength`, `agility`, `intellect`, `will`, and `critical_rate`.

`StatUnit` distinguishes:

- `flat`: a flat amount such as HP or Strength.
- `fraction`: a percentage stored as a fraction, so `0.05` displays as `5.0%`.
- `factor`: a multiplicative factor, displayed with a multiplication symbol.
- `number`: an amount whose presentation is otherwise unspecified.

```python
if build.stats is not None:
    print(build.stats.hp, build.stats.attack)
    print(build.stats.percent("critical_rate"))
    for stat in build.stats.values.values():
        print(stat.name, stat.display)
```

`percent()` accepts a supported name or property ID. It raises `KeyError` for an
absent property and `ValueError` for a property that is not fractional.
`value(property_id)` returns zero when that property is absent; inspect
`values` directly when your application needs to distinguish absence from zero.

`contributions` keeps source, property ID, formula, and input value for individual
modifiers. These are formula inputs, so summing them blindly does not reconstruct
a final stat. Unknown future property IDs are retained in the generic map.

## Equipment and weapons

`Equipment` contains slot, identity, name, rarity, set information, image links,
defense, enhancement counts, and `stat_lines`. Each `StatLine` contains display
metadata and all effects represented by that line. Unknown line values are `None`.

`EquipmentSet` contains its observed identity/name, canonical template ID when
known, equipped piece count, activation threshold, description, icon, and declared
static effects. Its computed `active` property compares piece count with the
threshold. `CharacterBuild.set_effects` includes static effects from active sets.

`Weapon` contains level, refinement, breakthrough, canonical identity, images,
base attack when known, skills, effects, and an optional `Gem`. Essence terms
retain independent point values and optional stable tags.

## Skills and talents

`Skill` exposes identity, name/type, observed level, maximum level, description,
parameters, effects, and optional forms. `TalentTree` groups nodes and potentials
with unlock identities and computed progress counts. Description text is
presentation data; conditional descriptions are not automatically treated as
unconditional numeric bonuses.

## Images and classification

`ImageLinks` keeps `skport`, `enka`, and `preferred`. Its computed `url` selects
the preferred nonempty candidate, falling back to the available alternative.
`effective_source` identifies the selection. Both candidate fields remain
available to the renderer. Selection does not test HTTP image availability.

Stable semantic keys describe elements, professions, weapon types, rarity,
and stat identities. Themes, colors, image cropping, and downloaded bitmap
caches belong in the application or card-rendering package.

## Reports and shared models

- `LiveStatus` contains player resources and activity meters. `ResourceMeter`
  retains current, maximum, recovery/refresh timestamps, and true progress ratio;
  current values may exceed maximum.
- `FactoryState` groups regions, settlements, exploration, cabins, and crew.
- `MonumentState` groups events, stages, medals, clear records, and team members.
- `ContractState` groups current/historical contracts, runs, modifiers, and enemies.
- `ItemSummary`, `MedalSummary`, `PlayerIdentity`, and `ModelIssue` provide shared
  item, medal, identity, and diagnostic information.

Some report metadata remains raw dictionaries where a complete typed conversion
is not yet exposed. Pull-history and wiki schemas are available as model
families, but the SDK's fetch helpers for those families currently return raw data.

See [character builds](../guides/character-builds.md) for static calculation
scope and [assets and images](../guides/assets-and-images.md) for cache behavior.
