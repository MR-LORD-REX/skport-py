# SKPORT response fixtures

These fixtures come from authenticated SKPORT reads and the official game
bulletin. They contain decoded response bodies. Example account IDs, role
IDs, editor IDs, player names, and pull sequences replace the original values.
The pull and attendance timestamps were adjusted. The captures exclude
account tokens, request headers, and intermediate credentials.

- `owner_binding.json`, `profile_snapshot.json`, `character_snapshot.json`,
  `monument_snapshot.json`, and `contract_snapshot.json` cover role selection,
  the public card, individual builds, and reports.
- `attendance.json` and `inventory.json` cover owner reads. Claim tests use
  an offline response with reward metadata from the attendance capture.
- `pull_character_special.json` and `pull_character_next.json` are successive
  pages from one stream. `pull_character_rerun.json` shows a versioned pool.
  `pull_weapon_pools.json` and `pull_weapon_empty.json` cover owner pool
  discovery and an empty weapon page. Offline tests construct additional
  weapon and pity edge cases.
- `wiki_operators.json` and `wiki_weapons.json` cover English catalogs. The
  article captures include English and Japanese responses. The large operator article was
  reduced to representative sections and tabs with their referenced documents.
- `char_banners.json`, `weapon_banners.json`, `news.json`, and `enums.json`
  cover public game reference data.

Large lists were reduced where the tests exercise the same response shape
with fewer entries.
