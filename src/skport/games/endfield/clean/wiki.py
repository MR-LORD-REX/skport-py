"""Normalize localized SKPORT wiki articles and public banner listings."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from skport.config import ImageSource
from skport.errors import DecodeError
from skport.games.endfield.clean.common import image_links, rarity, timestamp
from skport.games.endfield.models.banners import Banner, BannerItem, BannerWindow
from skport.games.endfield.models.base import ModelIssue
from skport.games.endfield.models.images import SemanticLabel
from skport.games.endfield.models.item import ItemSummary
from skport.games.endfield.models.wiki import (
    WikiAudio,
    WikiBlock,
    WikiEntry,
    WikiField,
    WikiItemRef,
    WikiPage,
    WikiSection,
    WikiSummary,
    WikiTableCell,
)

_QUOTES = {'"': '"', '“': '”', '「': '」', '『': '』', '«': '»'}


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _array(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string(value: Any) -> str:
    return str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else ""


def _list_field(data: Any, field: str, source: str) -> list[Any]:
    if not isinstance(data, dict) or not isinstance(data.get(field), list):
        raise DecodeError(f"{source} did not contain a list in {field!r}")
    return data[field]


def _tag_labels(category: dict[str, Any]) -> dict[str, str]:
    pending = list(_array(category.get("filterTagTree")))
    labels: dict[str, str] = {}
    while pending:
        tag = _object(pending.pop())
        key = _string(tag.get("id"))
        if key:
            labels[key] = _string(tag.get("name"))
        pending.extend(_array(tag.get("children")))
    return labels


def _inline_text(
    elements: Any, index: Mapping[str, WikiSummary] | None = None,
) -> tuple[str, list[WikiItemRef]]:
    parts: list[str] = []
    references: list[WikiItemRef] = []
    for value in _array(elements):
        element = _object(value)
        kind = element.get("kind")
        if kind == "text":
            parts.append(_string(_object(element.get("text")).get("text")))
        elif kind == "entry":
            ref = _object(element.get("entry"))
            item_id = _string(ref.get("id"))
            if item_id:
                raw_count = _string(ref.get("count"))
                count = int(raw_count) if raw_count.isdecimal() else None
                summary = index.get(item_id) if index is not None else None
                item = (
                    ItemSummary(id=item_id, name=summary.name, icon=summary.icon, description=summary.description)
                    if summary else None
                )
                references.append(
                    WikiItemRef(
                        id=item_id,
                        count=count,
                        display_type=_string(ref.get("showType")) or None,
                        item=item,
                    )
                )
                suffix = f" × {count}" if count else ""
                name = item.name if item and item.name else f"Wiki item {item_id}"
                parts.append(f"[{name}{suffix}]")
    return "".join(parts), references


def _block_text(blocks: list[WikiBlock]) -> str:
    return "\n".join(block.text for block in blocks).strip()


class _WikiDocument:
    """Resolve ordered local block IDs against a document's block map."""

    def __init__(
        self,
        document: dict[str, Any],
        preferred: ImageSource,
        issues: list[ModelIssue],
        path: str,
        index: Mapping[str, WikiSummary] | None,
    ) -> None:
        self.document = document
        self.block_map = _object(document.get("blockMap"))
        self.preferred = preferred
        self.issues = issues
        self.path = path
        self.index = index

    def read(self) -> list[WikiBlock]:
        return self._blocks(self.document.get("blockIds"), frozenset())

    def _blocks(self, ids: Any, ancestors: frozenset[str]) -> list[WikiBlock]:
        blocks: list[WikiBlock] = []
        for value in _array(ids):
            key = _string(value)
            node = _object(self.block_map.get(key))
            if key in ancestors or len(ancestors) >= 64:
                self.issues.append(
                    ModelIssue(
                        code="wiki_block_nesting",
                        message="An article block repeats an ancestor or exceeds the nesting limit",
                        path=f"{self.path}.{key}",
                    )
                )
            elif not node:
                self.issues.append(
                    ModelIssue(
                        code="wiki_block_missing",
                        message="An article block reference could not be resolved",
                        path=f"{self.path}.{key}",
                    )
                )
            else:
                blocks.append(self._block(key, node, ancestors | {key}))
        return blocks

    def _block(self, key: str, node: dict[str, Any], ancestors: frozenset[str]) -> WikiBlock:
        kind = _string(node.get("kind"))
        value = _object(node.get(kind))
        block = WikiBlock(id=key, source_type=kind)
        if kind == "text":
            block.kind = "text"
            block.text, block.item_refs = _inline_text(value.get("inlineElements"), self.index)
        elif kind == "image":
            block.kind = "image"
            block.image = image_links(_string(value.get("url")), preferred=self.preferred)
            block.text = _string(value.get("description"))
        elif kind == "table":
            block.kind = "table"
            block.rows = self._rows(value, ancestors)
            block.text = "\n".join(
                " | ".join(_block_text(cell.blocks) if cell else "" for cell in row)
                for row in block.rows
            )
        elif kind == "quote":
            block.kind = "quote"
            block.children = self._blocks(value.get("childIds"), ancestors)
            block.text = _block_text(block.children)
        elif kind == "externalVideo":
            block.kind = "video"
            block.url = _string(value.get("url")) or None
            block.image = image_links(_string(_object(value.get("cover")).get("url")), preferred=self.preferred)
            block.text = _string(value.get("description"))
        elif kind == "horizontalLine":
            block.kind = "separator"
        else:
            block.metadata = value
            block.children = self._blocks(value.get("childIds"), ancestors)
            block.text = _block_text(block.children) or _string(value.get("text"))
        return block

    def _rows(
        self, table: dict[str, Any], ancestors: frozenset[str]
    ) -> list[list[WikiTableCell | None]]:
        cell_map = _object(table.get("cellMap"))
        columns = [_string(column) for column in _array(table.get("columnIds"))]
        rows: list[list[WikiTableCell | None]] = []
        for row_id in map(_string, _array(table.get("rowIds"))):
            row: list[WikiTableCell | None] = []
            for column_id in columns:
                cell = _object(cell_map.get(f"{row_id}_{column_id}"))
                row.append(
                    WikiTableCell(
                        row_id=row_id,
                        column_id=column_id,
                        row_span=_span(cell.get("rowSpan")),
                        column_span=_span(cell.get("colSpan")),
                        blocks=self._blocks(cell.get("childIds"), ancestors),
                    ) if cell else None
                )
            rows.append(row)
        return rows


def _span(value: Any) -> int:
    text = _string(value)
    return max(int(text), 1) if text.isdecimal() else 1


def _wiki_summary(
    item: dict[str, Any],
    category: dict[str, Any],
    tags: dict[str, str],
    description: str,
    preferred: ImageSource,
) -> WikiSummary:
    item_id = _string(item.get("itemId"))
    if not item_id:
        raise DecodeError("wiki item did not contain an itemId")
    brief = _object(item.get("brief"))
    related = _object(brief.get("associate"))
    return WikiSummary(
        id=item_id,
        name=_string(item.get("name")) or _string(brief.get("name")),
        category=SemanticLabel(
            key=_string(category.get("id")),
            name=_string(category.get("name")),
            icons=image_links(_string(category.get("icon")), preferred=preferred),
        ),
        icon=image_links(_string(brief.get("cover")), preferred=preferred),
        description=description,
        related_game_id=_string(related.get("id")) or None,
        locale=_string(item.get("lang")) or None,
        tags=[SemanticLabel(key=key, name=tags.get(key, "")) for key in map(_string, _array(item.get("tagIds")))],
        dot_type=_string(brief.get("dotType")) or None,
    )


def wiki_catalog(data: Any, preferred: ImageSource) -> list[WikiSummary]:
    """Return each catalog item with its category, tags, and plain caption."""
    items: list[WikiSummary] = []
    for main in _list_field(data, "catalog", "wiki catalog"):
        for value in _array(_object(main).get("typeSub")):
            category = _object(value)
            tags = _tag_labels(category)
            for row in _array(category.get("items")):
                item = _object(row)
                description, _ = _inline_text(item.get("caption"))
                if not description.strip():
                    description = _string(_object(item.get("brief")).get("description"))
                items.append(_wiki_summary(item, category, tags, description.strip(), preferred))
    return items


def _entry(
    tab: dict[str, Any],
    data: dict[str, Any],
    documents: dict[str, Any],
    preferred: ImageSource,
    issues: list[ModelIssue],
    index: Mapping[str, WikiSummary] | None,
) -> WikiEntry:
    intro = _object(data.get("intro"))

    def resolve(value: Any) -> list[WikiBlock]:
        key = _string(value)
        if not key:
            return []
        if key not in documents:
            issues.append(
                ModelIssue(
                    code="wiki_document_missing",
                    message="A wiki tab points to an unavailable document",
                    path=f"documentMap.{key}",
                )
            )
            return []
        return _WikiDocument(_object(documents[key]), preferred, issues, f"documentMap.{key}", index).read()

    intro_blocks = resolve(intro.get("description"))
    blocks = resolve(data.get("content"))
    audio = [
        WikiAudio(
            id=_string(clip.get("id")),
            title=_string(clip.get("title")),
            transcript=_string(clip.get("profile")),
            url=_string(clip.get("resourceUrl")) or None,
        )
        for clip in map(_object, _array(data.get("audioList")))
    ]
    return WikiEntry(
        id=_string(tab.get("tabId")),
        name=_string(intro.get("name")) or _string(tab.get("title")),
        kind=_string(intro.get("type")),
        icon=image_links(_string(tab.get("icon")), preferred=preferred),
        illustration=image_links(_string(intro.get("imgUrl")), preferred=preferred),
        description=_block_text(intro_blocks),
        text=_block_text(blocks),
        intro_blocks=intro_blocks,
        blocks=blocks,
        audio=audio,
    )


def _item_summaries(entries: list[WikiEntry]) -> list[ItemSummary]:
    refs: dict[str, ItemSummary] = {}
    blocks = [block for entry in entries for block in (*entry.intro_blocks, *entry.blocks)]
    blocks.reverse()
    while blocks:
        block = blocks.pop()
        for item in block.item_refs:
            if item.id not in refs:
                refs[item.id] = item.item or ItemSummary(id=item.id)
        children = [child for row in block.rows for cell in row if cell for child in cell.blocks]
        blocks.extend(reversed(children))
        blocks.extend(reversed(block.children))
    return list(refs.values())


def _sections(
    document: dict[str, Any],
    preferred: ImageSource,
    issues: list[ModelIssue],
    index: Mapping[str, WikiSummary] | None,
) -> list[WikiSection]:
    widgets = _object(document.get("widgetCommonMap"))
    documents = _object(document.get("documentMap"))
    sections: list[WikiSection] = []
    for chapter in map(_object, _array(document.get("chapterGroup"))):
        for widget in map(_object, _array(chapter.get("widgets"))):
            widget_id = _string(widget.get("id"))
            title = _string(widget.get("title")).lstrip("/ ").strip()
            content = _object(widgets.get(widget_id))
            if not content:
                issues.append(
                    ModelIssue(
                        code="wiki_widget_missing",
                        message="A wiki section points to an unavailable widget",
                        path=f"widgetCommonMap.{widget_id}",
                    )
                )
            tab_data = _object(content.get("tabDataMap"))
            tabs = _array(content.get("tabList")) or [{"tabId": key, "title": title} for key in tab_data]
            entries = [
                _entry(tab, _object(tab_data.get(_string(tab.get("tabId")))), documents, preferred, issues, index)
                for tab in map(_object, tabs)
            ]
            fields = [
                WikiField(
                    id=_string(row.get("id")),
                    label=_string(row.get("label")).strip(),
                    value=_string(row.get("value")).strip(),
                )
                for row in map(_object, _array(content.get("tableList")))
            ]
            text = [part for entry in entries for part in (entry.description, entry.text) if part]
            text.extend(f"{field.label}: {field.value}" for field in fields)
            sections.append(
                WikiSection(
                    id=widget_id,
                    title=title,
                    chapter_id=_string(chapter.get("id")),
                    chapter=_string(chapter.get("title")),
                    kind=_string(content.get("type")),
                    text="\n\n".join(value for value in text if value),
                    entries=entries,
                    fields=fields,
                    items=_item_summaries(entries),
                )
            )
    return sections


def _quote_and_bio(description: str) -> tuple[str, str]:
    first, _, rest = description.partition("\n")
    first = first.strip()
    if len(first) > 1 and _QUOTES.get(first[0]) == first[-1]:
        return first[1:-1].strip(), rest.strip()
    return "", description


def wiki_page(data: Any, preferred: ImageSource, *, index: Mapping[str, WikiSummary] | None = None) -> WikiPage:
    """Flatten one article while preserving ordered widgets and linked content."""
    item = _object(_object(data).get("item"))
    category = _object(item.get("subType"))
    document = _object(item.get("document"))
    extra = _object(document.get("extraInfo"))
    brief_description = _object(item.get("brief")).get("description")
    issues: list[ModelIssue] = []
    description = _string(brief_description) or _block_text(
        _WikiDocument(_object(brief_description), preferred, issues, "brief.description", index).read()
    )
    summary = _wiki_summary(item, category, _tag_labels(category), description, preferred)
    sections = _sections(document, preferred, issues, index)
    quote, bio = _quote_and_bio(description)
    return WikiPage(
        summary=summary,
        illustration=image_links(_string(extra.get("illustration")), preferred=preferred),
        sections=sections,
        quote=quote,
        bio=bio,
        info_fields=[field for section in sections for field in section.fields],
        skill_entries=[
            entry for section in sections for entry in section.entries
            if summary.category.key == "1" and entry.kind and entry.intro_blocks
        ],
        lore=[
            entry for section in sections
            if section.title.casefold() in {"profile", "operator intel"} and section.kind == "common"
            for entry in section.entries
        ],
        issues=issues,
    )


def banners(data: Any, *, kind: Literal["character", "weapon"], preferred: ImageSource) -> list[Banner]:
    """Read public listings and preserve independent regional pool windows."""
    summaries: list[Banner] = []
    field = "chars" if kind == "character" else "weapons"
    for row in map(_object, _list_field(data, "list", "banner response")):
        banner_id = _string(row.get("id"))
        if not banner_id:
            raise DecodeError("banner did not contain an id")
        items = [
            BannerItem(
                id=_string(item.get("id")),
                name=_string(item.get("name")),
                icon=image_links(_string(item.get("pic")), preferred=preferred),
                rarity=rarity(item.get("rarity")) or None,
                dot_type=None if item.get("dotType") == "" else item.get("dotType"),
                link=_string(item.get("pcLink")) or None,
            )
            for item in map(_object, _array(row.get(field)))
        ]
        windows = []
        for region, start_key, end_key in (
            ("default", "poolStartAtTs", "poolEndAtTs"),
            ("europe", "europePoolStartAtTs", "europePoolEndAtTs"),
        ):
            start, end = timestamp(row.get(start_key)), timestamp(row.get(end_key))
            if start is not None or end is not None:
                windows.append(BannerWindow(region=region, starts_at=start, ends_at=end))
        summaries.append(
            Banner(
                id=banner_id,
                kind=kind,
                name=_string(row.get("name")),
                sort_id=row.get("sortId"),
                items=items,
                windows=windows,
                starts_at=timestamp(row.get("startAtTs")),
                ends_at=timestamp(row.get("endAtTs")),
            )
        )
    return summaries
