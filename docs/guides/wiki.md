# Wiki and banners

Use the wiki catalog to find an article ID, then fetch the article in the
same language. Catalog category `1` lists operators and `2` lists weapons.

```python
operators = await client.endfield.wiki_catalog(type_sub_id=1, lang="en")
if operators:
    page = await client.endfield.wiki_item(operators[0].id, lang="en")
    print(page.summary.name, page.quote)
    for skill in page.skill_entries:
        print(skill.name, skill.description or skill.text)
```

`WikiPage` exposes a quote, bio, overview fields, skill entries, and lore when
the localized article provides them. Its ordered `sections` retain article
headings, typed table cells, embedded images and media, and linked wiki IDs.
Use the section list to display unrecognized or differently structured content.
Coverage varies across articles and localizations. Missing or cyclic block
references appear in `page.issues`.

Use `index={entry.id: entry for entry in catalog}` to resolve item references
against catalogs you have loaded. The keys are wiki article IDs. Catalog
`related_game_id` identifies the associated item in game data. References
without a matching index entry retain their ID and quantity.

```python
character_banners = await client.endfield.char_banners(lang="en")
weapon_banners = await client.endfield.weapon_banners(lang="en")
for banner in character_banners + weapon_banners:
    print(banner.name, banner.starts_at, banner.ends_at)
    for window in banner.windows:
        print(window.region, window.starts_at, window.ends_at)
```

Each banner includes the listed items, their rarity markers, and regional
pool windows provided by SKPORT. Use owner pull history separately to inspect
the record streams for your account. [Pull history](pull-history.md)

See the runnable [wiki example](https://github.com/MR-LORD-REX/skport-py/blob/main/examples/wiki.py)
and [banners example](https://github.com/MR-LORD-REX/skport-py/blob/main/examples/banners.py).
