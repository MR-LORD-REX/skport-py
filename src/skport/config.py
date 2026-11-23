"""Validated deployment settings and service-specific language codes."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from skport.errors import ConfigError


class Region(StrEnum):
    """Deployment names; only GLOBAL is currently supported."""

    GLOBAL = "global"
    CN = "cn"


class Language(StrEnum):
    """SKPORT languages verified against the global web endpoints."""

    EN = "en"
    JA = "ja"
    KO = "ko"
    ZH_HANS = "zh-Hans"
    ZH_HANT = "zh-Hant"


LANGUAGE_ALIASES = {
    "en": Language.EN,
    "en-us": Language.EN,
    "en-gb": Language.EN,
    "ja": Language.JA,
    "ja-jp": Language.JA,
    "jp": Language.JA,
    "ko": Language.KO,
    "ko-kr": Language.KO,
    "kr": Language.KO,
    "zh-hans": Language.ZH_HANS,
    "zh-cn": Language.ZH_HANS,
    "chs": Language.ZH_HANS,
    "zh-hant": Language.ZH_HANT,
    "zh-tw": Language.ZH_HANT,
    "cht": Language.ZH_HANT,
}
SERVICE_LANGUAGES = {
    Language.EN: ("en-us", "en", "EN"),
    Language.JA: ("ja-jp", "ja", "JP"),
    Language.KO: ("ko-kr", "ko", "KR"),
    Language.ZH_HANS: ("zh-cn", "zh-cn", "CHS"),
    Language.ZH_HANT: ("zh-tw", "zh-tw", "CHT"),
}


def parse_language(value: str | Language) -> Language:
    """Normalize aliases without silently accepting unsupported languages."""
    if isinstance(value, Language):
        return value
    if not isinstance(value, str):
        raise ConfigError("language must be a string")
    key = value.strip().replace("_", "-").lower()
    try:
        return LANGUAGE_ALIASES[key]
    except KeyError as exc:
        raise ConfigError(f"unsupported SKPORT language {value!r}") from exc


def parse_region(value: str | Region) -> Region:
    """Reject deployments whose complete authentication protocol is unverified."""
    try:
        region = value if isinstance(value, Region) else Region(value.strip().lower())
    except (AttributeError, ValueError) as exc:
        raise ConfigError("unsupported region") from exc
    if region is not Region.GLOBAL:
        raise ConfigError("CN deployment is not supported yet")
    return region


def service_language(value: str | Language) -> str:
    """Return the regional query code used by news and pull records."""
    return SERVICE_LANGUAGES[parse_language(value)][0]


@dataclass(frozen=True, slots=True)
class Hosts:
    """Hosts used by the verified global deployment."""

    account: str = "https://as.gryphline.com"
    game: str = "https://zonai.skport.com"
    binding: str = "https://binding-api-account-prod.gryphline.com"
    webview: str = "https://ef-webview.gryphline.com"
    news: str = "https://game-hub.gryphline.com"

    @classmethod
    def for_region(cls, region: Region) -> Hosts:
        """Return verified hosts or reject an unsupported deployment."""
        parse_region(region)
        return cls()


@dataclass(frozen=True, slots=True)
class Protocol:
    """Constants for the global SKPORT web signature dialect."""

    app_code: str = "6eb76d4e13aa36e6"
    gacha_app_code: str = "3dacefa138426cfe"
    platform: str = "3"
    version: str = "1.0.0"
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36"
    )
    origin: str = "https://game.skport.com"
    bulletin_code: str = "endfield_U35PW8"


@dataclass(slots=True)
class ClientConfig:
    """Shared settings; refresh_interval is caller policy, not an expiry promise."""

    lang: Language = Language.EN
    region: Region = Region.GLOBAL
    timeout: float = 20.0
    per_token_concurrency: int = 1
    cooldown: float = 60.0
    min_interval: float = 0.0
    refresh_interval: float | None = None
    cache: bool = True
    cache_size: int = 512
    login_store: Path | None = None
    max_attempts: int = 3
    retry_backoff: float = 0.25
    user_agent: str = field(default_factory=lambda: Protocol().user_agent)

    @property
    def hosts(self) -> Hosts:
        """Hosts corresponding to the validated deployment."""
        return Hosts.for_region(self.region)

    @property
    def protocol(self) -> Protocol:
        """The deployed signing and OAuth constants."""
        return Protocol()

    def __post_init__(self) -> None:
        self.lang = parse_language(self.lang)
        self.region = parse_region(self.region)
        positive = {"timeout": self.timeout}
        if self.refresh_interval is not None:
            positive["refresh_interval"] = self.refresh_interval
        for name, value in positive.items():
            if not math.isfinite(value) or value <= 0:
                raise ConfigError(f"{name} must be finite and greater than zero")
        for name in ("cooldown", "min_interval", "retry_backoff"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ConfigError(f"{name} must be finite and nonnegative")
        for name in ("per_token_concurrency", "cache_size", "max_attempts"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ConfigError(f"{name} must be a positive integer")
        if self.login_store is not None:
            self.login_store = Path(self.login_store).expanduser()
