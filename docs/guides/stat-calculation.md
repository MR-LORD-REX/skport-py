# Stat calculation

`CharacterBuild.stats` is a static operator sheet calculated from the saved
loadout. SKPORT supplies character and weapon progression, equipment and its
enhancement slots, essence terms, and unlocked talent nodes. The SDK resolves
those records against one cached revision of Enka's public Endfield tables.
Public and owner builds share this pipeline. Use `build.asset_revision` to
identify the revision used for a result. [Enka data tables](https://github.com/EnkaNetwork/API-docs/tree/master/store/ef)

## Loadout inputs

- **Operator.** For each canonical base attribute, start with
  `BaseValue + AddValue * (level - 1)`. Attack Speed (property `15`) is divided
  by 100 to convert the table value into a factor. Base HP and ATK come from
  their per-level curves at `level - 1`. The sheet starts with Critical Damage
  `0.5` and Ultimate Gain `1.0`. Potential contributes all entries whose required
  level is at most the observed potential. Promotion is exposed as `evolution`
  on the build. The engine uses the observed level and unlocks in the formulas
  without a separate multiplier for promotion.
- **Weapon.** Add the canonical weapon ATK curve value at `weapon_level - 1`.
  When SKPORT supplies the effective weapon skill levels, the SDK matches
  those skills to canonical entries by their stable tags or passive keys.
  Otherwise it adds the refinement and breakthrough lower bounds, then adds
  essence points matching the skill's tag, capped at the sum of the two upper
  bounds. Essence raises effective skill levels. Each skill then contributes
  the properties in its canonical `PropMap` at that level. Level zero contributes
  nothing. A one-entry property curve applies at every positive level.
- **Equipment.** Base defense uses the first value on its curve. Other
  modifiers use the zero-based enhancement count of the corresponding SKPORT
  stat line. A combined line such as Cryo and Electric Damage applies that
  count to both property curves. An equipment set contributes the level-one
  `PropMap` of its canonical set skill once three matching pieces are equipped.
- **Unlocked attributes.** Each unique unlocked attribute node contributes all
  its canonical values. Modifier IDs `10000` and `10001` resolve to the
  operator's main and secondary attribute IDs.

The sheet covers canonical static modifiers and the two unconditional operator
passives described below. Conditional skill and set effects, team buffs,
tactical-item activation, and damage rotations are outside its scope.

## Combine modifiers

Each property has five formula stages. Sum `BaseAddition` into `base`,
`BaseMultiplier` into `base_ratio`, `BaseFinalAddition` into `final_add`, and
`Addition` into `add`. Multiply `BaseFinalMultiplier` entries into `final_factor`,
which starts at `1`.

```text
value = (base * (1 + base_ratio) + final_add) * final_factor + add
```

When an existing property has no explicit base contribution, its starting base
is `1` for factor properties and `0` for other units. For example, cooldown
factors `0.9` and `0.8` combine to `0.72`. With a base of `100`, a base ratio
of `0.10`, a final addition of `5`, a final factor of `0.9`, and an addition
of `7`, the unrounded result is `110.5`.

## Derive HP, Treatment Received, and ATK

The engine uses whole attribute values at this stage. It floors Strength, Will,
and the relevant main, secondary, or passive attributes after combining their
modifiers.

- **HP.** Each point of Strength contributes `5` HP at `BaseAddition`, so HP
  multipliers apply to this bonus along with the other base HP.
- **Treatment Received.** Each point of Will adds `0.001` at `Addition`, or
  0.1 percentage points. Direct Treatment Received modifiers also contribute.
- **ATK.** Let `pre_attribute_atk` be ATK evaluated after the existing ATK
  modifiers. Add `pre_attribute_atk * (0.005 * main + 0.002 * secondary)` at
  `Addition`. Each point in the main attribute adds 0.5% of that ATK, and each
  point in the secondary attribute adds 0.2%.
- **Catcher and Lifeng.** The highest unlocked tier of the supported passive
  applies. Catcher adds `floor(Will / 10)` to DEF at tier one and
  `floor(Will / 10) * 1.2` at tier two. Lifeng adds
  `pre_attribute_atk * (Intellect + Will) * 0.001` at tier one, and uses
  `0.0015` at tier two. Both passives use the `Addition` stage.

For example, with base HP `100`, pre-attribute ATK `10`, and Strength `20`
and Will `30` as main and secondary attributes, the sheet has `200` HP,
`3.0%` Treatment Received, and `11` ATK after flooring `11.6`. This example
assumes no other modifiers or operator-specific passives.

## Rounding and diagnostics

Known flat properties, including HP, ATK, DEF, the four attributes, and Arts
Intensity, are floored for output. The engine adds a small `1e-9` allowance at
the floor boundary to absorb floating-point error. Fractions and factors keep
their calculated precision. Fraction display uses decimal half-up rounding
to one percentage place by default, so `0.564` appears as `56.4%`.

`build.stats.values` gives the final value and unit for each property ID.
`build.stats.contributions` gives the source, formula stage, and amount of
each input. Inspect it alongside the asset revision to trace a result. An
unsupported formula, unresolved canonical match, or value outside an asset
curve can make the sheet unavailable. With default settings, inspect
`build.calculation_state` and `build.issues` when `build.stats` is `None`.
Use `ClientConfig(missing_assets="raise")` to receive the error or
`ClientConfig(calculate_stats=False)` to skip calculation. [Assets and images](assets-and-images.md)

## How the numbers are checked

The maintainer's offline reference tests use four recorded Enka loadouts for
Si, Liino, Arcane, and Yvonne. They compare 39 reference values from the Enka
stat display, including HP, ATK, DEF, attributes, Critical Rate, healing, and
selected damage and Ultimate Gain values. Integer expectations must match
exactly. Fraction expectations allow an absolute difference of `0.0006`
(0.06 percentage points). These comparisons establish agreement with the
recorded Enka display for the sampled loadouts. [Upstream display references](https://github.com/ShresthVaibhav/akef/blob/55a2bfe3c10d058ee8aba6d0959fd1c616b7f7d0/tests/test_enka.py#L16-L35)

Separate fixture tests resolve and calculate eight captured SKPORT builds.
They check the canonical revision, equipment and essence mapping, populated
core stats, and contribution sources. Hand-computed cases exercise modifier
order, factor defaults, rounding, essence caps, shared gear enhancement slots,
set thresholds, talent deduplication, and the two passives. The fixture suite
lives under the maintainer's ignored `local/tests` directory. Direct
comparisons against in-game screenshots remain unverified.
