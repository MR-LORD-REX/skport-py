# Wiki and banners

The examples run inside an open `SkportClient` context with a configured
viewer token. Operator references and upgrade guides use published game data.
The inventory example also requires an owner token.

## Find articles

Discover the localized category tree and its filters with `wiki_categories()`.
Main category `1` is the Endfield Database, with subcategories `1` for operators,
`2` for weapons and `6` for item files. Omit `type_sub_id` to list all articles in
one main category.

```python
wiki = client.endfield
categories = await wiki.wiki_categories(lang="en")
operators = await wiki.wiki_catalog(type_main_id=1, type_sub_id=1, lang="en")
matches = await wiki.wiki_search("Kay", category=(1, 1), lang="en")

batch = await wiki.wiki_items([100, 109, 128], lang="en")
for item in batch.items.values():
    print(item.id, item.name, item.icon.url)
print(batch.missing_ids)
```

`wiki_search()` returns service results and applies the optional `(main_id,
sub_id)` filter locally. Catalogs are also useful for localized lookup when the
service returns few matches. `wiki_items()` retrieves summaries in batches of
up to 30 and reports requested article IDs omitted by the service. Filter and
association metadata are available when the underlying endpoint supplies them.

`wiki_index()` indexes discovered categories, or just the pairs you pass as
`categories=[(1, 1), (1, 2)]`. Its `items` map is keyed by wiki article ID.
`by_game_id(game_id, type_sub_id=1)` returns all associated candidates in that
subcategory. `WikiSummary.related_game_id` represents the game identity when
SKPORT publishes an association.

## Read an article

```python
page = await wiki.wiki_item(1993, lang="en", index=batch.items)
print(page.summary.name, page.quote, page.illustration.url)
for section in page.sections:
    print(section.title, section.text)
```

`WikiPage` exposes the quote, bio, overview fields, skill entries and lore when
the article provides them. The ordered sections retain inline formatting,
lists, table spans, links, images and media. `index` lets the parser resolve
references from a previously loaded batch or catalog. An unresolved reference
retains its wiki ID and any published quantity. Missing or cyclic block
references appear in `page.issues`. An absent article raises `WikiNotFound`.

## Prepare an operator reference card

```python
operator = await wiki.wiki_operator(1993, lang="en")
print(operator.summary.name, operator.illustration.url)
for snapshot in operator.stats:
    print(snapshot.level, snapshot.values)
for skill in operator.skills:
    print(skill.name, skill.kind, skill.description)
```

Show each stat snapshot at its published level and each skill metric at its
published rank. When the overview and a level tab disagree, the snapshot keeps
the overview value and lists the other observation in `alternatives`. Use the
article's illustration, profile copy, rarity, element, profession, weapon type,
and faction when available. Coverage varies by article and locale. For
calculated player stats and loadouts, see the [character build guide](character-builds.md).

`wiki_operator()` and `wiki_upgrade_guide()` accept an optional `fallback_lang`.
When the requested locale has no article, they retry in that language.
`requested_locale` records the original request and `summary.locale` identifies
the article used. An existing partial translation returns the sections it
publishes.

## Prepare an upgrade guide

```python
guide = await wiki.wiki_upgrade_guide(1993, lang="en")
promotions = [step.id for step in guide.steps if step.kind == "promotion"]
total = guide.total(promotions)
for amount in total.materials:
    item = amount.summary
    print(item.name if item else amount.wiki_id, amount.quantity, item.icon.url if item else None)
print(total.complete, total.unpriced_step_ids)
```

The guide groups published steps by `kind` for leveling, promotion, outfitting,
talents, skill ranks and potential. `step.costs` carries the observed recipes.
Each cost's materials include an article ID, a quantity when published, and a
resolved summary when available. The total covers the selected steps. A
conflicting cost can be selected explicitly with
`cost_choices={step_id: zero_based_option_index}`. Use `missing_groups`,
`unpriced_step_ids` and `issues` to display gaps in coverage. Leveling totals
reproduce the wiki's published Auto Fill recipes for selected milestones.

`wiki_material()` provides acquisition and usage sections for a material.
When recipe columns are recognized, recipes expose their requirements, inputs
and outputs with references back to the article table.

```python
material = await wiki.wiki_material(128, lang="en")
for section in material.acquisition + material.usage:
    print(section.title, section.text)
for recipe in material.recipes:
    print(recipe.requirement, recipe.inputs, recipe.outputs)
```

## Read public banners

```python
character_banners = await wiki.char_banners(lang="en")
weapon_banners = await wiki.weapon_banners(lang="en")
for banner in character_banners + weapon_banners:
    print(banner.name, banner.starts_at, banner.ends_at)
    for window in banner.windows:
        print(window.region, window.starts_at, window.ends_at)
    for item in banner.items:
        print(item.name, item.wiki_id, item.rarity)
```

The banner methods preserve regional pool windows and the listing's own item ID.
They resolve missing item names from verified article links by default. Pass
`enrich=False` to skip that lookup. Wiki reads use a one-hour cache and banner
reads use a ten-minute cache by default. Pass `ttl=0` to bypass the cache.
For account-specific pull records, see the [pull history guide](pull-history.md).

## Enrich an owner's inventory

```python
inventory = await wiki.inventory(token=owner_token, lang="en", raw=False, enrich=True)
for item in inventory.weapons.values():
    print(item.id, item.wiki_item_id, item.name, item.icon.url, item.count)
```

`enrich=True` fills available display metadata from verified wiki associations
and the same role's card. The typed entries preserve the inventory's ownership,
counts and progression, including zero or unknown counts. Each resolved display
field can identify its source and locale. Read `inventory.issues` for lookup
failures or ambiguous joins. The endpoint covers operators, weapons, gear and
tactical items. A separate material balance is required to compute upgrade
shortfalls. See [owner accounts](owner-accounts.md) for role selection.

See the runnable [wiki example](https://github.com/MR-LORD-REX/skport-py/blob/main/examples/wiki.py)
and [banners example](https://github.com/MR-LORD-REX/skport-py/blob/main/examples/banners.py).
