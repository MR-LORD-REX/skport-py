"""Normalize localized SKPORT wiki articles and public banner listings."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import ValidationError

from skport.config import ImageSource
from skport.errors import DecodeError, WikiNotFound
from skport.games.endfield.clean.common import image_links, rarity, timestamp
from skport.games.endfield.endpoints import WIKI_INFO
from skport.games.endfield.models.banners import Banner, BannerItem, BannerWindow
from skport.games.endfield.models.base import ModelIssue
from skport.games.endfield.models.images import ImageLinks, SemanticLabel
from skport.games.endfield.models.item import ItemSummary
from skport.games.endfield.models.wiki import (
    WikiAssociation,
    WikiAudio,
    WikiBlock,
    WikiEntry,
    WikiField,
    WikiInline,
    WikiItemRef,
    WikiListItem,
    WikiMaterial,
    WikiMaterialRecipe,
    WikiPage,
    WikiSection,
    WikiSummary,
    WikiTableCell,
    WikiTag,
)
from skport.games.endfield.models.wiki_catalog import WikiBatchResult, WikiCatalogTree, WikiCategory

_QUOTES = {'"': '"', '“': '”', '「': '」', '『': '』', '«': '»'}
_LORE_LABELS = {
    "en": {"profile", "operator intel"},
    "ja": {"個人情報", "プロファイル"},
    "ko": {"오퍼레이터 정보", "파일"},
}
_MATERIAL_LABELS = {
    "en": ({"source", "item source"}, {"usage", "item usage"}, "applicable formulas"),
    "ja": ({"入手方法"}, {"使い方"}, "レシピ"),
    "ko": ({"획득 방법"}, {"사용처"}, "사용 가능 조합 공식"),
}
_RECIPE_HEADERS = {
    "en": ("materials needed", "production"),
    "ja": ("素材消費", "生産"),
    "ko": ("필요 재료", "제작 대상"),
}


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


def _integer(value: Any) -> int | None:
    text = _string(value)
    return int(text) if text.isdecimal() else None


def _image(url: str, preferred: ImageSource) -> ImageLinks:
    try:
        return image_links(url, preferred=preferred)
    except ValidationError:
        raise DecodeError("wiki artwork did not contain a valid image URL") from None


def _wiki_tag(row: dict[str, Any], group_id: str | None = None) -> WikiTag:
    key = _string(row.get("id"))
    return WikiTag(
        key=key,
        name=_string(row.get("name")),
        value=_string(row.get("value")),
        type=_integer(row.get("type")),
        hidden=row.get("hide") if isinstance(row.get("hide"), bool) else None,
        group_id=group_id,
        children=[_wiki_tag(child, key) for child in map(_object, _array(row.get("children")))],
    )


def _tag_labels(category: dict[str, Any]) -> dict[str, WikiTag]:
    pending = [_wiki_tag(row) for row in map(_object, _array(category.get("filterTagTree")))]
    labels: dict[str, WikiTag] = {}
    while pending:
        tag = pending.pop()
        if tag.key:
            labels[tag.key] = tag
        pending.extend(tag.children)
    return labels


def _category(row: dict[str, Any], preferred: ImageSource) -> WikiCategory:
    return WikiCategory(
        key=_string(row.get("id")),
        name=_string(row.get("name")),
        icons=_image(_string(row.get("icon")), preferred),
        parent_id=_string(row.get("fatherTypeId")) or None,
        status=_integer(row.get("status")),
        style=_integer(row.get("style")),
        position=_integer(row.get("position")),
        subcategories=[_category(sub, preferred) for sub in map(_object, _array(row.get("typeSub")))],
        filters=[_wiki_tag(tag) for tag in map(_object, _array(row.get("filterTagTree")))],
    )


def wiki_categories(data: Any, preferred: ImageSource, locale: str) -> WikiCatalogTree:
    """Keep both levels of the localized wiki category taxonomy."""
    rows = _list_field(data, "catalog", "wiki catalog")
    return WikiCatalogTree(locale=locale, categories=[_category(_object(row), preferred) for row in rows])


def _inline_runs(elements: Any, index: Mapping[str, WikiSummary] | None = None) -> list[WikiInline]:
    runs: list[WikiInline] = []
    for value in _array(elements):
        element = _object(value)
        kind = _string(element.get("kind"))
        payload = _object(element.get(kind))
        run = WikiInline(
            kind="unknown",
            source_type=kind,
            bold=element.get("bold") is True,
            italic=element.get("italic") is True,
            underline=element.get("underline") is True,
            color=_string(element.get("color")) or None,
            metadata={key: value for key, value in element.items() if key not in {
                "kind", "bold", "italic", "underline", "color",
            }},
        )
        if kind == "text":
            run.kind = "text"
            run.text = _string(payload.get("text"))
            if set(payload) == {"text"}:
                run.metadata.pop(kind, None)
        elif kind == "entry":
            run.kind = "entry"
            item_id = _string(payload.get("id"))
            if item_id:
                raw_count = _string(payload.get("count"))
                count = int(raw_count) if raw_count.isdecimal() else None
                summary = index.get(item_id) if index is not None else None
                item = (
                    ItemSummary(id=item_id, name=summary.name, icon=summary.icon, description=summary.description)
                    if summary else None
                )
                run.reference = WikiItemRef(
                    id=item_id,
                    count=count,
                    display_type=_string(payload.get("showType")) or None,
                    item=item,
                )
                suffix = f" × {count}" if count else ""
                name = item.name if item and item.name else f"Wiki item {item_id}"
                run.text = f"[{name}{suffix}]"
                if payload.keys() <= {"id", "count", "showType"} and (not raw_count or count is not None):
                    run.metadata.pop(kind, None)
        elif kind == "link":
            run.kind = "link"
            run.url = _string(payload.get("link")) or None
            run.text = _string(payload.get("text")) or run.url or ""
            if payload.keys() <= {"link", "text"}:
                run.metadata.pop(kind, None)
        elif kind == "pronunciation":
            run.kind = "pronunciation"
            content = _string(payload.get("content"))
            base, delimiter, reading = content.removesuffix("|").partition("|")
            if delimiter and base and reading and "|" not in reading:
                run.text = base
                run.reading = reading
            else:
                run.text = content
        runs.append(run)
    return runs


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
            block.runs = _inline_runs(value.get("inlineElements"), self.index)
            block.text = "".join(run.text for run in block.runs)
            block.item_refs = [run.reference for run in block.runs if run.reference is not None]
        elif kind == "list":
            block.kind = "list"
            block.list_kind = _string(value.get("kind")) or None
            block.list_items = self._list_items(value, ancestors)
            block.metadata = {field: metadata for field, metadata in value.items() if field not in {
                "id", "kind", "itemIds", "itemMap", "childIds",
            }}
            if block.list_items:
                block.text = "\n".join(item.text for item in block.list_items).strip()
            else:
                block.children = self._children(node, value, ancestors)
                block.text = _block_text(block.children)
        elif kind == "image":
            block.kind = "image"
            block.image = _image(_string(value.get("url")), self.preferred)
            block.text = _string(value.get("description"))
        elif kind == "table":
            block.kind = "table"
            block.row_ids = list(map(_string, _array(value.get("rowIds"))))
            block.column_ids = list(map(_string, _array(value.get("columnIds"))))
            row_header = value.get("rowHeader")
            column_header = value.get("colHeader")
            block.row_header = row_header if isinstance(row_header, bool) else None
            block.column_header = column_header if isinstance(column_header, bool) else None
            block.rows = self._rows(value, block.row_ids, block.column_ids, ancestors)
            block.metadata = {field: metadata for field, metadata in value.items() if field not in {
                "id", "rowIds", "columnIds", "rowHeader", "colHeader", "cellMap",
            }}
            block.text = "\n".join(
                " | ".join(cell.text if cell else "" for cell in row)
                for row in block.rows
            )
        elif kind == "quote":
            block.kind = "quote"
            block.children = self._children(node, value, ancestors)
            block.text = _block_text(block.children)
        elif kind == "externalVideo":
            block.kind = "video"
            block.url = _string(value.get("url")) or None
            block.image = _image(_string(_object(value.get("cover")).get("url")), self.preferred)
            block.text = _string(value.get("description"))
        elif kind == "horizontalLine":
            block.kind = "separator"
        else:
            block.metadata = value
            block.children = self._children(node, value, ancestors)
            block.text = _block_text(block.children) or _string(value.get("text"))
        return block

    def _children(
        self, node: dict[str, Any], value: dict[str, Any], ancestors: frozenset[str]
    ) -> list[WikiBlock]:
        ids = dict.fromkeys(map(_string, _array(node.get("childIds")) + _array(value.get("childIds"))))
        return self._blocks(list(ids), ancestors)

    def _list_items(self, value: dict[str, Any], ancestors: frozenset[str]) -> list[WikiListItem]:
        item_map = _object(value.get("itemMap"))
        items = []
        for item_id in map(_string, _array(value.get("itemIds"))):
            item = _object(item_map.get(item_id))
            if not item:
                self.issues.append(ModelIssue(
                    code="wiki_list_item_missing",
                    message="A wiki list points to an unavailable item",
                    path=f"{self.path}.{_string(value.get('id'))}.{item_id}",
                ))
            items.append(WikiListItem(id=item_id, blocks=self._blocks(item.get("childIds"), ancestors)))
        return items

    def _rows(
        self, table: dict[str, Any], row_ids: list[str], column_ids: list[str], ancestors: frozenset[str]
    ) -> list[list[WikiTableCell | None]]:
        cell_map = _object(table.get("cellMap"))
        rows: list[list[WikiTableCell | None]] = []
        for row_id in row_ids:
            row: list[WikiTableCell | None] = []
            for column_id in column_ids:
                cell = _object(cell_map.get(f"{row_id}_{column_id}"))
                row.append(
                    WikiTableCell(
                        row_id=row_id,
                        column_id=column_id,
                        row_span=_span(cell.get("rowSpan")),
                        column_span=_span(cell.get("colSpan")),
                        background_color=_string(cell.get("backgroundColor")) or None,
                        vertical_align=_string(cell.get("verticalAlign")) or None,
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
    tags: dict[str, WikiTag],
    preferred: ImageSource,
    *,
    main: dict[str, Any] | None = None,
    description: str | None = None,
) -> WikiSummary:
    item_id = _string(item.get("itemId"))
    if not item_id:
        raise DecodeError("wiki item did not contain an itemId")
    brief = _object(item.get("brief"))
    related = _object(brief.get("associate"))
    game_id = _string(related.get("id")) or None
    main = main if main is not None else _object(item.get("mainType"))
    main_id = _string(main.get("id") or item.get("mainTypeId") or category.get("fatherTypeId"))
    sub_id = _string(category.get("id") or item.get("subTypeId"))
    facets = [tags.get(key) or WikiTag(key=key) for key in map(_string, _array(item.get("tagIds")))]
    caption = _inline_runs(item.get("caption"))
    if description is None:
        description = "".join(run.text for run in caption).strip() or _string(brief.get("description")).strip()
    return WikiSummary(
        id=item_id,
        name=_string(item.get("name")) or _string(brief.get("name")),
        category=SemanticLabel(
            key=sub_id,
            name=_string(category.get("name")),
            icons=_image(_string(category.get("icon")), preferred),
        ),
        icon=_image(_string(brief.get("cover")), preferred),
        description=description,
        caption=caption,
        related_game_id=game_id,
        locale=_string(item.get("lang")) or None,
        tags=[SemanticLabel(key=tag.key, name=tag.name) for tag in facets],
        dot_type=_string(brief.get("dotType")) or None,
        main_type_id=main_id or None,
        sub_type_id=sub_id or None,
        main_category=SemanticLabel(key=main_id, name=_string(main.get("name"))),
        association=WikiAssociation(
            game_id=game_id,
            kind=_string(related.get("type")),
            name=_string(related.get("name")),
            dot_type=_string(related.get("dotType")) or None,
        ) if game_id else None,
        facets=facets,
        redirect_url=_string(brief.get("redirectLink")) or None,
        mobile_redirect_url=_string(brief.get("redirectLinkMobile")) or None,
        hide_detail_cover=brief.get("disableCoverShowInDetail") is True,
        status=_integer(item.get("status")),
        published_at=timestamp(item.get("publishedAtTs")),
        last_audit_passed_at=timestamp(item.get("lastAuditPassedAt")),
    )


def wiki_catalog(data: Any, preferred: ImageSource) -> list[WikiSummary]:
    """Return each catalog item with its category, tags, and plain caption."""
    items: list[WikiSummary] = []
    for main in map(_object, _list_field(data, "catalog", "wiki catalog")):
        for value in _array(main.get("typeSub")):
            category = _object(value)
            tags = _tag_labels(category)
            for row in _array(category.get("items")):
                item = _object(row)
                items.append(_wiki_summary(item, category, tags, preferred, main=main))
    return items


def wiki_search(data: Any, preferred: ImageSource) -> list[WikiSummary]:
    """Normalize results while preserving service ordering."""
    results: list[WikiSummary] = []
    for item in map(_object, _list_field(data, "items", "wiki search")):
        category = _object(item.get("subType"))
        results.append(_wiki_summary(item, category, _tag_labels(category), preferred))
    return results


def wiki_batch(data: Any, ids: list[str], preferred: ImageSource, locale: str) -> WikiBatchResult:
    """Resolve the batch endpoint's item and category maps by their published IDs."""
    rows = _object(data)
    for key in ("items", "mainTypes", "subTypes"):
        if not isinstance(rows.get(key), dict):
            raise DecodeError(f"wiki batch did not contain a map in {key!r}")
    main_types = _object(rows["mainTypes"])
    sub_types = _object(rows["subTypes"])
    items: dict[str, WikiSummary] = {}
    tag_labels = {key: _tag_labels(_object(row)) for key, row in sub_types.items()}
    for key in ids:
        if key not in rows["items"]:
            continue
        item = _object(rows["items"][key])
        if _string(item.get("itemId")) != key:
            raise DecodeError("wiki batch key did not match its itemId")
        sub_id = _string(item.get("subTypeId"))
        items[key] = _wiki_summary(
            item,
            _object(sub_types.get(sub_id)),
            tag_labels.get(sub_id, {}),
            preferred,
            main=_object(main_types.get(_string(item.get("mainTypeId")))),
        )
    return WikiBatchResult(
        locale=locale,
        requested_ids=ids,
        items=items,
        missing_ids=[key for key in ids if key not in items],
        main_categories={key: _category(_object(row), preferred) for key, row in main_types.items()},
        subcategories={key: _category(_object(row), preferred) for key, row in sub_types.items()},
    )


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

    intro_id = _string(intro.get("description"))
    content_id = _string(data.get("content"))
    intro_blocks = resolve(intro_id)
    blocks = resolve(content_id)
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
        title=_string(tab.get("title")),
        name=_string(intro.get("name")) or _string(tab.get("title")),
        kind=_string(intro.get("type")),
        icon=_image(_string(tab.get("icon")), preferred),
        illustration=_image(_string(intro.get("imgUrl")), preferred),
        description=_block_text(intro_blocks),
        text=_block_text(blocks),
        intro_blocks=intro_blocks,
        intro_id=intro_id,
        blocks=blocks,
        content_id=content_id,
        audio=audio,
    )


def _item_summaries(entries: list[WikiEntry]) -> list[ItemSummary]:
    refs: dict[str, ItemSummary] = {}
    for entry in entries:
        for root in (*entry.intro_blocks, *entry.blocks):
            for block in root.walk():
                for item in block.item_refs:
                    if item.id not in refs:
                        refs[item.id] = item.item or ItemSummary(id=item.id)
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
            tabs = list(map(_object, _array(content.get("tabList"))))
            listed_ids = dict.fromkeys(_string(tab.get("tabId")) for tab in tabs)
            for tab_id in listed_ids:
                if tab_id not in tab_data:
                    issues.append(ModelIssue(
                        code="wiki_tab_missing",
                        message="A declared wiki tab has no content in the tab map",
                        path=f"widgetCommonMap.{widget_id}.tabDataMap.{tab_id}",
                    ))
            tabs.extend({"tabId": key, "title": title} for key in tab_data if key not in listed_ids)
            entries = [
                _entry(tab, _object(tab_data.get(_string(tab.get("tabId")))), documents, preferred, issues, index)
                for tab in tabs
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
    response = _object(data)
    if "item" in response and response["item"] is None:
        raise WikiNotFound("wiki article was unavailable in the requested locale", path=WIKI_INFO)
    item = _object(response.get("item"))
    for field in ("document", "brief"):
        if item.get(field) is not None and not isinstance(item[field], dict):
            raise DecodeError(f"wiki item field {field!r} did not contain an object", path=WIKI_INFO)
    category = _object(item.get("subType"))
    document = _object(item.get("document"))
    extra = _object(document.get("extraInfo"))
    brief_description = _object(item.get("brief")).get("description")
    issues: list[ModelIssue] = []
    description_blocks = _WikiDocument(_object(brief_description), preferred, issues, "brief.description", index).read()
    description = _string(brief_description) or _block_text(description_blocks)
    summary = _wiki_summary(item, category, _tag_labels(category), preferred, description=description)
    sections = _sections(document, preferred, issues, index)
    illustration = _image(_string(extra.get("illustration")), preferred)
    quote, bio = _quote_and_bio(description)
    return WikiPage(
        summary=summary,
        illustration=illustration if illustration.url else summary.icon,
        sections=sections,
        quote=quote,
        bio=bio,
        description_blocks=description_blocks,
        info_fields=[field for section in sections for field in section.fields],
        skill_entries=[
            entry for section in sections for entry in section.entries
            if summary.category.key == "1" and entry.kind and entry.intro_blocks
        ],
        lore=[
            entry for section in sections
            if section.title.casefold() in _LORE_LABELS.get(summary.locale or "en", set()) and section.kind == "common"
            for entry in section.entries
        ],
        issues=issues,
    )


def _recipe_rows(
    section: WikiSection, entry: WikiEntry, table: WikiBlock, headers: tuple[str, str], issues: list[ModelIssue],
) -> list[WikiMaterialRecipe]:
    source = f"{section.id}.{entry.id}.{table.id}"
    first_row = table.rows[0] if table.rows else []
    labels = [cell.text.casefold() if cell else "" for cell in first_row]
    if len(labels) != 3 or tuple(labels[1:]) != headers:
        issues.append(ModelIssue(
            code="wiki_material_recipe_layout",
            message="A recipe table has an unrecognized input or output column",
            path=source,
        ))
        return []

    recipes: list[WikiMaterialRecipe] = []
    requirement = ""
    requirement_end = 0
    requirement_label = first_row[0].text if first_row[0] else ""
    for index, row in enumerate(table.rows[1:], start=1):
        if len(row) != 3:
            continue
        condition, input_cell, output_cell = row
        if condition is not None:
            requirement = condition.text
            requirement_end = index + condition.row_span
        inputs = input_cell.item_refs if input_cell else []
        outputs = output_cell.item_refs if output_cell else []
        if not inputs or not outputs:
            issues.append(ModelIssue(
                code="wiki_material_recipe_items_missing",
                message="A recipe row has no item references for its inputs or outputs",
                path=f"{source}.{index}",
            ))
            continue
        assert input_cell is not None
        recipes.append(WikiMaterialRecipe(
            section_id=section.id,
            entry_id=entry.id,
            table_id=table.id,
            row_id=input_cell.row_id,
            name=section.title,
            requirement=requirement if index < requirement_end else "",
            requirement_label=requirement_label,
            inputs=inputs,
            outputs=outputs,
        ))
    return recipes


def wiki_material(page: WikiPage) -> WikiMaterial:
    """Project the localized sources, uses, and published recipes from an article."""
    locale = page.summary.locale or "en"
    acquisition_labels, usage_labels, recipe_chapter = _MATERIAL_LABELS.get(locale, (set(), set(), ""))
    material = WikiMaterial(summary=page.summary, issues=list(page.issues))
    for section in page.sections:
        labels = {section.title.casefold(), section.chapter.casefold()}
        if labels & acquisition_labels:
            material.acquisition.append(section)
        elif labels & usage_labels:
            material.usage.append(section)
        elif recipe_chapter and section.chapter.casefold() == recipe_chapter:
            material.recipe_sections.append(section)
            for entry in section.entries:
                for root in entry.blocks:
                    for block in root.walk():
                        if block.kind == "table":
                            material.recipes.extend(_recipe_rows(
                                section, entry, block, _RECIPE_HEADERS[locale], material.issues,
                            ))
    return material


def _banner_wiki_id(link: str, kind: Literal["character", "weapon"]) -> str | None:
    try:
        url = urlsplit(link)
        if (url.scheme, url.netloc, url.path) != ("https", "wiki.skport.com", "/endfield/detail"):
            return None
    except ValueError:
        return None
    query = parse_qs(url.query)
    if query.get("mainTypeId") != ["1"] or query.get("subTypeId") != ["1" if kind == "character" else "2"]:
        return None
    ids = query.get("gameEntryId", [])
    return ids[0] if len(ids) == 1 and ids[0].isascii() and ids[0].isdecimal() else None


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
                icon=_image(_string(item.get("pic")), preferred),
                rarity=rarity(item.get("rarity")) or None,
                dot_type=None if item.get("dotType") == "" else item.get("dotType"),
                link=_string(item.get("pcLink")) or None,
                wiki_id=_banner_wiki_id(_string(item.get("pcLink")), kind),
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
