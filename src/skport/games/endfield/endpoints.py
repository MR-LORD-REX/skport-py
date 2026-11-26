"""Endfield endpoint paths across SKPORT and official game services."""

from typing import Final

DETAIL: Final = "/api/v1/game/endfield/card/detail"
CHARACTER: Final = "/api/v1/game/endfield/card/char"
CONTRACT: Final = "/api/v1/game/endfield/card/crisis-contract"
MONUMENT: Final = "/api/v1/game/endfield/card/indie-hard"
ENUMS: Final = "/web/v1/game/endfield/enums"
WIKI_CATALOG: Final = "/web/v1/wiki/item/catalog"
WIKI_INFO: Final = "/web/v1/wiki/item/info"
WIKI_ITEMS: Final = "/web/v1/wiki/item/list"
WIKI_SEARCH: Final = "/web/v1/wiki/item/search"
CHAR_BANNERS: Final = "/web/v1/wiki/char-pool"
WEAPON_BANNERS: Final = "/web/v1/wiki/weapon-pool"
ATTENDANCE: Final = "/web/v1/game/endfield/attendance"
INVENTORY: Final = "/web/v1/game/endfield/team/user-game-data"
PULL_BINDING: Final = "/account/binding/v1/binding_list"
PULL_TOKEN: Final = "/account/binding/v1/u8_token_by_uid"
CHAR_PULLS: Final = "/api/record/char"
WEAPON_POOLS: Final = "/api/record/weapon/pool"
WEAPON_PULLS: Final = "/api/record/weapon"
NEWS: Final = "/bulletin/v2/aggregate"
OWNER_PATHS: Final = frozenset({ATTENDANCE, INVENTORY})
