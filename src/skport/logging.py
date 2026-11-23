"""Opt-in logging that exposes safe metadata and protects credentials."""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Mapping
from weakref import WeakSet

REDACTED = "<redacted>"
SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "cred",
        "salt",
        "sign",
        "token",
        "account_token",
        "wtoken",
    }
)
_SECRET = re.compile(
    r"""(?i)(["']?(?:account_token|authorization|cookie|set-cookie|cred|salt|sign|wtoken|token)["']?\s*[:=]\s*)(?:["'][^"']*["']|[^\s,;&}]+)"""
)
_URL_QUERY = re.compile(r"(https?://[^\s?]+)\?[^\s]+")
_LOG = logging.getLogger("skport")
_LOG.addHandler(logging.NullHandler())
_CONFIGURED_HANDLERS: WeakSet[logging.Handler] = WeakSet()


class RedactionFilter(logging.Filter):
    """Mask known secret fields in formatted records as a defensive measure."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = _URL_QUERY.sub(r"\1", record.getMessage())
        record.msg = _SECRET.sub(lambda match: match.group(1) + REDACTED, message)
        record.args = ()
        return True


def get_logger(name: str = "skport") -> logging.Logger:
    """Return a namespaced logger without root configuration."""
    logger = logging.getLogger(name if name == "skport" or name.startswith("skport.") else f"skport.{name}")
    if not any(isinstance(item, RedactionFilter) for item in logger.filters):
        logger.addFilter(RedactionFilter())
    return logger


def configure(level: int | str = logging.INFO, *, handler: logging.Handler | None = None) -> None:
    """Attach or update an application-requested handler for this library."""
    _LOG.setLevel(level)
    _LOG.propagate = False
    existing = [item for item in _LOG.handlers if item in _CONFIGURED_HANDLERS]
    if existing and handler is None:
        return
    for item in existing:
        _LOG.removeHandler(item)
        _CONFIGURED_HANDLERS.discard(item)
    sink = handler or logging.StreamHandler()
    sink.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    sink.addFilter(RedactionFilter())
    _CONFIGURED_HANDLERS.add(sink)
    _LOG.addHandler(sink)


def fingerprint(secret: str) -> str:
    """Return an opaque account identifier suitable for request diagnostics."""
    return hashlib.sha256(secret.encode()).hexdigest()[:16]


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return a copy with credentials and authorization values removed."""
    return {key: REDACTED if key.lower() in SENSITIVE_HEADERS else value for key, value in headers.items()}
