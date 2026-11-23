"""SKPORT account and community endpoint paths."""

from typing import Final

CARDS: Final = "/api/v1/game/cards"
BINDING: Final = "/api/v1/game/player/binding"
PROFILE: Final = "/api/v2/user"
WEB_PROFILE: Final = "/web/v2/user"
USER_ITEMS: Final = "/api/v1/user/items"
ACCOUNT_BASIC: Final = "/user/info/v1/basic"
THIRD_PARTY: Final = "/user/info/v1/third_party"
GRANT: Final = "/user/oauth2/v2/grant"
CREDENTIAL: Final = "/web/v1/user/auth/generate_cred_by_code"
REFRESH: Final = "/web/v1/auth/refresh"
