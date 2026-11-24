"""Official Enka image URLs, independent of Enka player API availability."""

from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit

from skport.errors import AssetError

ENKA_IMAGE_BASE = "https://enka.network/ui/ef/"


def enka_image(path: str | None) -> str | None:
    """Normalize a canonical icon/art path to its official CDN URL."""
    if not path or not path.strip():
        return None
    value = path.strip().replace("\\", "/")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme == "https" and parsed.netloc == "enka.network" and parsed.path.startswith("/ui/ef/"):
            return value
        raise AssetError("canonical image URL must use the official Enka CDN")
    if parsed.query or parsed.fragment or ".." in PurePosixPath(value).parts:
        raise AssetError("canonical image path is invalid")
    value = value.lstrip("/")
    if value.startswith("ui/ef/"):
        value = value[len("ui/ef/") :]
    if not PurePosixPath(value).suffix:
        value += ".png"
    return ENKA_IMAGE_BASE + quote(value, safe="/%_-.")


def enka_item_image(path: str | None) -> str | None:
    """Resolve weapon and essence icons into the official itemicon directory.

    Some raw store entries contain only a root-level filename, while the CDN
    serves that same item under itemicon.
    """
    normalized = enka_image(path)
    if normalized is None:
        return None
    filename = PurePosixPath(urlsplit(normalized).path).name
    return ENKA_IMAGE_BASE + "itemicon/" + filename
