from __future__ import annotations

from dataclasses import dataclass, field

from skport.config import Language, Protocol
from skport.transport.signer import sign


@dataclass(frozen=True, slots=True)
class RequestSignature:
    """A signed request's transport headers."""

    headers: dict[str, str] = field(repr=False)
    timestamp: str
    signature: str = field(repr=False)


def account_headers(*, language: Language, user_agent: str) -> dict[str, str]:
    """Headers for the OAuth host, which uses `x-language`."""
    return {
        "User-Agent": user_agent,
        "x-language": language.value,
        "Content-Type": "application/json",
    }


def game_headers(
    *,
    language: Language,
    protocol: Protocol,
    user_agent: str,
    cred: str,
    salt: str,
    path: str,
    body: str = "",
    game_role: str | None = None,
) -> RequestSignature:
    """Build and sign headers for a Zonai/game request.

    Public target reads deliberately omit `sk-game-role`. Owner-scoped
    requests pass the role header explicitly.
    """
    signed = sign(
        path,
        body,
        salt,
        platform=protocol.platform,
        version=protocol.version,
    )
    timestamp = signed["timestamp"]
    headers = {
        "cred": cred,
        "platform": protocol.platform,
        "vName": protocol.version,
        "timestamp": timestamp,
        "sign": signed["sign"],
        "sk-language": language.value,
        "Content-Type": "application/json",
        "User-Agent": user_agent,
        "Origin": protocol.origin,
        "Referer": f"{protocol.origin}/",
        "Accept": "*/*",
    }
    if game_role:
        headers["sk-game-role"] = game_role
    return RequestSignature(headers, timestamp, signed["sign"])


def plain_headers(*, user_agent: str) -> dict[str, str]:
    """Unauthenticated headers for binding/news-style hosts."""
    return {"User-Agent": user_agent, "Content-Type": "application/json"}
