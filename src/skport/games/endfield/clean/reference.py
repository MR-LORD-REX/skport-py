"""Normalize localized enum groups and game bulletin text."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

from skport.config import ImageSource
from skport.games.endfield.clean.common import semantic, timestamp, wire_list, wire_object
from skport.games.endfield.models.reference import EnumCatalog, Notice

_BLOCK_TAGS = {"article", "br", "div", "h1", "h2", "h3", "li", "p", "section", "tr"}
_HIDDEN_TAGS = {"script", "style"}


class _BulletinText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _HIDDEN_TAGS:
            self.hidden += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _HIDDEN_TAGS:
            self.hidden = max(0, self.hidden - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)

    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self.parts).splitlines())
        return "\n".join(line for line in lines if line)


def enum_catalog(data: Any, locale: str, preferred: ImageSource) -> EnumCatalog:
    """Preserve each service group with its keys and localized values."""
    groups = {
        key: [semantic(row, preferred) for row in value if isinstance(row, dict) and row.get("key")]
        for key, value in wire_object(data, "game enums").items()
        if isinstance(value, list)
    }
    return EnumCatalog(groups=groups, locale=locale)


def notices(data: Any, locale: str) -> list[Notice]:
    """Read the bulletin list and turn its HTML into plain display text."""
    raw = wire_object(data, "news")
    result = []
    for value in wire_list(raw.get("list"), "news stories"):
        row = wire_object(value, "news story")
        content = wire_object(row.get("data") or {}, "news story content")
        parser = _BulletinText()
        parser.feed(str(content.get("html") or ""))
        parser.close()
        button = row.get("jumpButton") or {}
        link = content.get("url") or content.get("link")
        if not link and isinstance(button, dict):
            link = button.get("url") or button.get("link")
        result.append(Notice(
            id=str(row.get("cid") or ""),
            title=str(row.get("title") or ""),
            header=str(row.get("header") or ""),
            text=parser.text(),
            category=str(row.get("tab") or ""),
            locale=locale,
            published_at=timestamp(row.get("startAt")),
            url=link if isinstance(link, str) and link else None,
        ))
    return result
