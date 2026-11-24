# Models, assets and calculations

The output layer uses Pydantic models with snake_case fields, separate from raw
SKPORT responses and card templates. Import models from
`skport.games.endfield.models` or their focused modules. Use
`model_dump(mode="json")` or `model_dump_json()` for serialization.

## Schema families

- `identity.py`: `PlayerIdentity` keeps the SKPORT social ID, game UID and
  server separate. `CharacterIdentity` retains the opaque SKPORT character ID,
  resolved Enka template/string IDs and optional display-variant IDs.
- `images.py`: `ImageLinks` stores image alternatives; `CharacterImages`
  separates avatar, portrait, splash and half-body artwork. `SemanticLabel`
  stores a stable classification key, localized name and optional icons.
- `character.py`: `CharacterSummary` holds identity, classifications, artwork
  and progression. `CharacterBuild` adds owner, calculated stats, skills,
  talents, equipment, equipment sets, weapon, tactical item and provenance.
- `stats.py`: `StatBlock` preserves a map of property IDs to `StatValue`, main
  and sub attributes, and individual `StatContribution` records.
  `StatModifier` preserves the formula and unit of an input modifier.
- `equipment.py`: `Equipment` retains its slot, identity, defense, enhancement
  and `StatLine` entries. Body, arms and both accessory positions are distinct.
  Combined lines retain every affected stat in `effects` and `stat_ids`.
- `equipment_set.py`: `EquipmentSet` groups observed set metadata, piece count,
  activation threshold, description, artwork and canonical static modifiers.
- `weapon.py`: `Weapon` contains level, breakthrough, refinement, base attack,
  skills and effects. `Gem` and `GemTerm` keep essence identity and independent
  socket points.
- `skills.py` and `talents.py`: `Skill`, `SkillForm`, `TalentNode`, `Potential`
  and `TalentTree` retain levels, descriptions, unlocks and canonical effects.
- `profile.py`: `PlayerCard` combines player identity, artwork, mission,
  authority/world levels, dates, counts, medals, characters and region state.
  `source_scope`, `roster_complete` and `ProfilePrivacy` describe exposure.
- `progress.py`: `ResourceMeter` and `LiveStatus` keep resource/activity values
  and times. Current values may exceed maximum; `ratio` preserves overflow.
- `world.py`: `FactoryState`, `RegionProgress`, `Settlement`, `AreaProgress`,
  `Cabin` and `CrewMember` represent regional and spaceship state.
- `endgame.py`: monument and contract reports share event stages, runs,
  lightweight team members, enemies, medals and modifier metadata.
- `pulls.py` and `wiki.py`: schemas for pull history and wiki articles. Their
  complete typed fetch adapters are pending; current endpoints return raw data.
- `item.py` and `base.py`: common item/medal summaries, output behavior and
  diagnostic `ModelIssue` records.

Element, profession, rarity and stat identities give a card renderer stable
keys for its palette. Themes, layout, comparison bars, image color extraction
and custom artwork belong in `skport-cards`. Two builds of the same character
already supply the data for a comparison card.

## Image sources

`ImageLinks` retains `skport`, `enka` and `preferred`. Its computed `.url`
selects the preferred nonempty candidate; `.effective_source` records the
selection. Both candidate fields remain available when preference changes.

~~~py
from skport import SkportClient

async with SkportClient(tokens=tokens, icon_source="skport") as client:
    build = await client.endfield.character(skport_id=skport_id, index=0)
    art_url = build.images.splash.url
    alternative = build.images.splash.enka
~~~

SKPORT is the default in `ClientConfig`. Use `icon_source="enka"` on a client
or its configuration to prefer Enka. Portrait/half-body records remain
SKPORT-only where no equivalent canonical Enka artwork is available. Unknown
canonical assets do not acquire fabricated Enka links. Some decorative stat
icons have only Enka metadata; a renderer can map their stable property IDs to
local icons.

The SDK selects URLs from metadata without checking their HTTP availability.
It does not fetch bitmap files. During an Enka outage, a renderer should use
the retained SKPORT candidate or its own cached artwork.

## Cache policy and updates

Canonical tables come from the official Enka asset repository and are cached
as coherent revisioned snapshots. Calculations do not require Enka's live
Endfield player endpoint. `asset_revision` on each build and player card
records which canonical snapshot was used.

The relevant `ClientConfig` defaults are:

- `icon_source="skport"`: prefer SKPORT artwork.
- `calculate_stats=True`: calculate static sheet values when possible.
- `missing_assets="partial"`: retain renderable wire data when canonical
  resolution or calculation fails.
- `assets_auto_update=False`: use a valid cache without requesting Enka.
- `assets_offline=False`: permit an initial download and explicit updates.
- `assets_dir=None`: use the user cache under `skport/enka`.
- `assets_ref="master"`: upstream branch or commit for asset downloads.

With a valid snapshot, the first build loads cached data. Without one, the
first typed build downloads a snapshot unless `assets_offline=True`. Client
construction and authentication warming do not download assets. Setting
`assets_auto_update=True` opts into an initial refresh and a refresh attempt
when a build cannot resolve against the loaded revision; a failed refresh
retains valid cached data.

Refresh explicitly through the main client:

~~~py
update = await client.update_assets()
print(update.changed, update.previous_revision, update.snapshot.revision)
~~~

The update validates the snapshot and installs it atomically. Failure raises
`AssetError`, preserving the previous valid disk and memory snapshot. Later
requests use a successful update; previously returned models are unchanged.

`assets_offline=True` blocks Enka asset requests, including `update_assets()`.
SKPORT requests still run. With cached character and loadout data, older
characters can produce builds and calculated stats while Enka is unavailable,
using SKPORT icon URLs. A new character, weapon or equipment piece absent from
that snapshot may still return a renderable partial build.

## Partial and strict builds

`CharacterBuild.status` is `complete` when canonical resolution and the
requested calculation succeed; otherwise it is `partial`.
`calculation_state` distinguishes `calculated`, `unavailable` and
`not_requested`. Read `issues` for resolution/update diagnostics.

Missing canonical data does not become an invented zero-value stat block.
Partial builds retain SKPORT names, progression, artwork and loadout metadata,
with `stats=None` when calculation cannot complete. Unresolved gear values and
weapon base attack remain `None` when they are unknown.

Set `ClientConfig(missing_assets="raise")` to require canonical data and
propagate resolution/calculation errors. Set `calculate_stats=False` to skip
arithmetic; the result has `calculation_state="not_requested"` while canonical
resolution can still enrich metadata.

## Static calculation and stat units

The calculator uses canonical character and weapon curves, potential
modifiers, observed weapon skill levels, gear enhancements, unlocked
attribute nodes and activated equipment sets. It derives attribute-based HP,
attack and treatment values, and handles the explicitly supported
unconditional character passives. `contributions` records each source,
formula and numeric input.

`equipment_sets` includes observed sets even below their activation threshold.
Each set exposes its piece count, `active` state and declared static `effects`.
`CharacterBuild.set_effects` contains only canonical static modifiers from
active sets. A conditional set description can remain visible even when it
has no unconditional sheet modifier.

Conditional combat effects, team buffs and tactical-item activation are
outside this static sheet. Descriptions do not become guessed numeric
modifiers, and calculated stats are not a damage simulation.

`StatUnit` distinguishes `flat`, `fraction`, `factor` and `number`. Fractional
values are stored as fractions: a critical rate of `0.05` displays as `5.0%`.
A gain value can exceed `1.0`; no percent cap is imposed. Formula factors stay
factors. Use `StatValue.display` or `StatBlock.percent()` for formatting.
Unknown future property IDs are retained in `StatBlock.values`.

~~~py
if build.stats is not None:
    print(build.stats.hp, build.stats.attack, build.stats.defense)
    print(build.stats.percent("critical_rate"))
    print(build.stats.values[44].display)
~~~

## Owner roster and character selection

`owned_card(token=...)`, `owned_characters(token=..., full=True)` and
`owned_character(token=..., index=0)` fetch the supplied token owner's data.
An optional `role` selects one of that token's bound roles. A public target or
dummy token cannot substitute for owner authentication.

Single-character methods require exactly one of `char_id`, `name` or `index`.
`char_id` is the opaque SKPORT ID, names are normalized and must be unique,
and indexes select nonnegative positions in the returned list. Owner roster
requests use the returned roster rather than configured public showcase IDs.
Both public and owner builds use the same asset and calculation pipeline.

## Remaining card adapters

Operator, profile, factory, activity, monument and contract data already have
typed client methods. Pull history/pity and wiki article schemas still need
complete fetch adapters. Live event summaries and some factory metadata retain
raw dictionaries for later normalization. Card rendering, pagination, layout,
theme palettes and bitmap caching remain work for `skport-cards`.
