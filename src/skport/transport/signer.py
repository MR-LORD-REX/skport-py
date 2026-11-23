from __future__ import annotations

import hashlib
import hmac
import json
import time


def compact_json(value: object) -> str:
    """Serialize JSON exactly as the SKPORT signer hashes it."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def base_headers(timestamp: str, *, platform: str = "3", version: str = "1.0.0") -> dict[str, str]:
    """Build the ordered fixed header object used inside the signature."""
    return {"platform": platform, "timestamp": timestamp, "dId": "", "vName": version}


def sign_payload(
    path: str, body: str, salt: str, timestamp: str, *, platform: str, version: str
) -> dict[str, str]:
    """Sign a request and return the fixed header object plus `sign`."""
    headers = base_headers(timestamp, platform=platform, version=version)
    encoded = compact_json(headers)
    message = f"{path}{body}{timestamp}{encoded}"
    digest = hmac.new(salt.encode(), message.encode(), hashlib.sha256).hexdigest()
    return {**headers, "sign": hashlib.md5(digest.encode()).hexdigest()}


def sign(
    path: str,
    body: str,
    salt: str,
    *,
    timestamp: str | None = None,
    platform: str = "3",
    version: str = "1.0.0",
) -> dict[str, str]:
    """Sign a SKPORT path and request body.

    Args:
        path: URL path without the host, exactly as it appears in the request.
        body: Canonical query string for GET requests or compact JSON for POST.
        salt: Per-credential signing key.
        timestamp: Optional Unix seconds; the current time is used by default.
        platform: SKPORT client platform code.
        version: SKPORT web API version.

    Returns:
        The fixed signing headers, including `platform`, `timestamp`,
        `dId`, `vName` and `sign`.
    """
    ts = timestamp or str(int(time.time()))
    return sign_payload(path, body, salt, ts, platform=platform, version=version)
