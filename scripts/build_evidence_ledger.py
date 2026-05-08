#!/usr/bin/env python3
"""Build a unified evidence ledger from MinerU output files."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import sys
from typing import Any, Iterable


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
CONTENT_LIST_KEYS = ("content", "contents", "blocks", "data", "items", "result")
MIDDLE_BLOCK_KEYS = ("layout_dets", "para_blocks", "preproc_blocks", "blocks", "spans", "lines")
TEXT_KEYS = ("text", "content", "md", "html", "caption", "title", "text_content")
IMAGE_PATH_KEYS = ("img_path", "image_path", "path", "src", "file", "filename")
PAGE_KEYS = ("page", "page_no", "page_num", "page_number")
PAGE_INDEX_KEYS = ("page_idx", "page_index")

MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)|<img[^>]+src=[\"']([^\"']+)[\"'][^>]*>", re.I)
EN_LABEL_RE = re.compile(r"\b(?P<kind>fig(?:ure)?\.?|table)\s*[:.]?\s*(?P<num>S?\d+[A-Za-z0-9_.-]*)", re.I)
CN_LABEL_RE = re.compile(r"(?P<kind>[图表])\s*(?P<num>S?\d+[A-Za-z0-9_.-]*)")
HTML_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
HTML_CELL_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


def add_warning(warnings: list[dict], code: str, message: str, **extra: Any) -> None:
    warning = {"code": code, "message": message}
    warning.update({key: value for key, value in extra.items() if value is not None})
    warnings.append(warning)


def truncate_text(value: Any, max_chars: int) -> str:
    text = str(value)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)] + "…"


def summarize_raw(value: Any, max_chars: int, depth: int = 2) -> Any:
    if depth <= 0:
        if isinstance(value, (dict, list)):
            return f"<{type(value).__name__}>"
        if isinstance(value, str):
            return truncate_text(value, max_chars)
        return value
    if isinstance(value, dict):
        result = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= 20:
                result["__truncated__"] = True
                break
            result[str(key)] = summarize_raw(item, max_chars, depth - 1)
        return result
    if isinstance(value, list):
        result = [summarize_raw(item, max_chars, depth - 1) for item in value[:20]]
        if len(value) > 20:
            result.append({"__truncated__": True, "remaining": len(value) - 20})
        return result
    if isinstance(value, str):
        return truncate_text(value, max_chars)
    return value


def raw_for_output(raw: Any, mode: str, max_chars: int) -> Any:
    if mode == "none":
        return None
    if mode == "full":
        return raw
    return summarize_raw(raw, max_chars)


def rel_path(path: pathlib.Path, root: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def path_ref(path: pathlib.Path, root: pathlib.Path) -> dict:
    return {
        "path": str(path),
        "relative_path": rel_path(path, root),
        "exists": path.exists(),
    }


def safe_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def stable_id(prefix: str, number: int) -> str:
    return f"{prefix}-{number:06d}"


def short_id(prefix: str, number: int) -> str:
    return f"{prefix}-{number:04d}"


def load_json_file(path: pathlib.Path, warnings: list[dict], strict: bool) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        if strict:
            raise RuntimeError(f"Could not parse JSON file {path}: {exc}") from exc
        add_warning(warnings, "json_parse_failed", "Could not parse JSON file", path=str(path), detail=str(exc))
        return None


def find_full_md(root: pathlib.Path) -> pathlib.Path | None:
    direct = root / "full.md"
    if direct.exists():
        return direct
    candidates = sorted(root.rglob("full.md"))
    if candidates:
        return candidates[0]
    markdown = sorted(root.rglob("*.md"))
    return markdown[0] if markdown else None


def find_content_list_files(root: pathlib.Path) -> list[pathlib.Path]:
    return sorted(root.rglob("*_content_list.json"))


def find_middle_files(root: pathlib.Path) -> list[pathlib.Path]:
    return sorted(root.rglob("*_middle.json"))


def find_images_dir(root: pathlib.Path) -> pathlib.Path | None:
    direct = root / "images"
    if direct.is_dir():
        return direct
    candidates = sorted(path for path in root.rglob("images") if path.is_dir())
    return candidates[0] if candidates else None


def load_manifest(root: pathlib.Path, warnings: list[dict], strict: bool) -> tuple[dict | None, pathlib.Path | None]:
    path = root / "mineru_manifest.json"
    if not path.exists():
        add_warning(warnings, "manifest_missing", "mineru_manifest.json was not found", path=str(path))
        return None, None
    data = load_json_file(path, warnings, strict)
    return (data if isinstance(data, dict) else None), path


def classify_markdown_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return "blank"
    if MARKDOWN_IMAGE_RE.search(stripped):
        return "image_ref"
    if is_markdown_table_line(stripped):
        return "table_row"
    if extract_label(stripped):
        return "caption_hint"
    if stripped.startswith("#"):
        return "heading"
    return "text"


def read_markdown_lines(md_path: pathlib.Path, root: pathlib.Path, max_context_chars: int) -> list[dict]:
    lines = md_path.read_text(encoding="utf-8", errors="replace").splitlines()
    records = []
    for line_no, line in enumerate(lines, start=1):
        records.append(
            {
                "id": stable_id("md-line", line_no),
                "line": line_no,
                "text": line,
                "context": truncate_text(line.strip(), max_context_chars),
                "kind_hint": classify_markdown_line(line),
                "markdown_ref": {
                    "path": str(md_path),
                    "relative_path": rel_path(md_path, root),
                    "line_start": line_no,
                    "line_end": line_no,
                },
            }
        )
    return records


def is_markdown_table_line(line: str) -> bool:
    stripped = line.strip()
    return "|" in stripped and not stripped.startswith("![") and not stripped.lower().startswith("<img")


def split_markdown_cells(line: str) -> list[str]:
    stripped = line.rstrip("\n")
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return stripped.split("|")


def is_separator_row(cells: list[str]) -> bool:
    if not cells:
        return False
    return all(re.fullmatch(r"\s*:?-{2,}:?\s*", cell or "") for cell in cells)


def parse_markdown_table(raw_lines: list[str], start_line: int, table_id: str) -> dict:
    parsed_rows = []
    for offset, raw_line in enumerate(raw_lines):
        cells = split_markdown_cells(raw_line)
        parsed_rows.append({"line": start_line + offset, "cells": cells, "raw": raw_line})

    header_cells: list[str] = []
    data_rows = parsed_rows
    separator_line = None
    if len(parsed_rows) >= 2 and is_separator_row(parsed_rows[1]["cells"]):
        header_cells = [cell.strip() for cell in parsed_rows[0]["cells"]]
        data_rows = parsed_rows[2:]
        separator_line = parsed_rows[1]["line"]

    rows = []
    for row_index, row in enumerate(data_rows, start=1):
        cells = []
        for column_index, raw_cell in enumerate(row["cells"], start=1):
            cells.append(
                {
                    "column_index": column_index,
                    "text": raw_cell.strip(),
                    "original_value": raw_cell,
                    "line": row["line"],
                }
            )
        rows.append({"row_index": row_index, "line": row["line"], "cells": cells})

    return {
        "id": table_id,
        "type": "table",
        "source": "markdown",
        "start_line": start_line,
        "end_line": start_line + len(raw_lines) - 1,
        "separator_line": separator_line,
        "raw_lines": raw_lines,
        "headers": header_cells,
        "rows": rows,
    }


def extract_markdown_tables(lines: list[dict]) -> list[dict]:
    tables = []
    current: list[str] = []
    start_line: int | None = None
    for record in lines:
        if is_markdown_table_line(record["text"]):
            if not current:
                start_line = record["line"]
            current.append(record["text"])
        else:
            if start_line is not None and len(current) >= 2:
                tables.append(parse_markdown_table(current, start_line, short_id("md-table", len(tables) + 1)))
            current = []
            start_line = None
    if start_line is not None and len(current) >= 2:
        tables.append(parse_markdown_table(current, start_line, short_id("md-table", len(tables) + 1)))
    return tables


def find_markdown_image_refs(lines: list[dict], root: pathlib.Path) -> list[dict]:
    refs = []
    for record in lines:
        for match in MARKDOWN_IMAGE_RE.finditer(record["text"]):
            alt_text = match.group(1) or ""
            target = match.group(2) or match.group(3) or ""
            refs.append(
                {
                    "id": short_id("md-image", len(refs) + 1),
                    "alt_text": alt_text,
                    "target": target,
                    "image_ref": resolve_image_path(target, root),
                    "markdown_ref": record["markdown_ref"],
                    "line": record["line"],
                }
            )
    return refs


def find_caption_like_lines(lines: list[dict]) -> list[dict]:
    captions = []
    for record in lines:
        label = extract_label(record["text"])
        if label:
            captions.append(
                {
                    "id": short_id("caption-md", len(captions) + 1),
                    "type": "caption",
                    "source": "markdown",
                    "text": record["text"].strip(),
                    "label": label["label"],
                    "label_kind": label["kind"],
                    "label_key": label["key"],
                    "raw_label": label["raw_label"],
                    "markdown_ref": record["markdown_ref"],
                    "page": None,
                    "page_index": None,
                    "provenance": {"sources": ["markdown"], "confidence": "medium"},
                }
            )
    return captions


def iter_content_blocks(data: Any, source_file: pathlib.Path, warnings: list[dict]) -> list[tuple[int, dict, str | None]]:
    if isinstance(data, list):
        return [(idx, item if isinstance(item, dict) else {"value": item}, None) for idx, item in enumerate(data)]
    if isinstance(data, dict):
        for key in CONTENT_LIST_KEYS:
            value = data.get(key)
            if isinstance(value, list):
                return [(idx, item if isinstance(item, dict) else {"value": item}, key) for idx, item in enumerate(value)]
        for key, value in data.items():
            if isinstance(value, list) and value and all(isinstance(item, dict) for item in value[:5]):
                return [(idx, item, str(key)) for idx, item in enumerate(value)]
    add_warning(warnings, "content_list_schema_unknown", "Could not find a content block list", path=str(source_file))
    return []


def raw_type(block: dict) -> str | None:
    for key in ("type", "category", "block_type", "content_type"):
        value = block.get(key)
        if value is not None:
            return str(value)
    return None


def classify_content_block(block: dict) -> str:
    kind = (raw_type(block) or "").lower()
    if "table" in kind:
        return "table"
    if any(token in kind for token in ("image", "figure", "fig")):
        return "figure"
    if "caption" in kind:
        return "caption"
    if any(token in kind for token in ("equation", "formula")):
        return "equation"
    if any(token in kind for token in ("text", "paragraph", "title", "heading")):
        return "text"
    text = extract_block_text(block)
    if text and extract_label(text):
        return "caption"
    return "unknown"


def extract_block_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [extract_block_text(item) for item in value]
        parts = [part for part in parts if part]
        return "\n".join(parts) if parts else None
    if not isinstance(value, dict):
        return None
    for key in TEXT_KEYS:
        item = value.get(key)
        if isinstance(item, str):
            return item
    for key in ("spans", "lines", "children"):
        item = value.get(key)
        if isinstance(item, list):
            text = extract_block_text(item)
            if text:
                return text
    return None


def extract_block_page(block: dict, parent_page: tuple[int | None, int | None] | None = None) -> tuple[int | None, int | None]:
    page = None
    page_index = None
    for key in PAGE_KEYS:
        if key in block:
            page = safe_int(block.get(key))
            break
    for key in PAGE_INDEX_KEYS:
        if key in block:
            page_index = safe_int(block.get(key))
            break
    if page is None and page_index is not None:
        page = page_index + 1
    if page_index is None and page is not None:
        page_index = page - 1 if page > 0 else page
    if page is None and page_index is None and parent_page is not None:
        return parent_page
    return page, page_index


def normalize_bbox_value(value: Any, source: str) -> dict | None:
    if isinstance(value, list):
        if len(value) >= 4 and all(isinstance(item, (int, float)) for item in value[:4]):
            return {"x0": value[0], "y0": value[1], "x1": value[2], "y1": value[3], "source": source, "coordinate_system": "mineru"}
        if value and all(isinstance(item, (list, tuple)) for item in value):
            return {"points": value, "source": source, "coordinate_system": "mineru"}
    if isinstance(value, dict):
        if all(key in value for key in ("x0", "y0", "x1", "y1")):
            return {"x0": value["x0"], "y0": value["y0"], "x1": value["x1"], "y1": value["y1"], "source": source, "coordinate_system": "mineru"}
        if all(key in value for key in ("left", "top", "right", "bottom")):
            return {"x0": value["left"], "y0": value["top"], "x1": value["right"], "y1": value["bottom"], "source": source, "coordinate_system": "mineru"}
        if all(key in value for key in ("left", "top", "width", "height")):
            return {
                "x0": value["left"],
                "y0": value["top"],
                "x1": value["left"] + value["width"],
                "y1": value["top"] + value["height"],
                "source": source,
                "coordinate_system": "mineru",
            }
        if "points" in value:
            return {"points": value["points"], "source": source, "coordinate_system": "mineru"}
    return None


def extract_block_bbox(block: dict, source: str) -> dict | None:
    for key in ("bbox", "box", "position", "rect"):
        if key in block:
            bbox = normalize_bbox_value(block[key], source)
            if bbox:
                return bbox
    return None


def resolve_image_path(value: str, root: pathlib.Path) -> dict:
    clean = value.strip().strip("\"'")
    if not clean:
        return {"path": None, "relative_path": None, "raw": value, "exists": False}
    clean_path = pathlib.Path(clean)
    if clean_path.is_absolute():
        candidate = clean_path
    else:
        candidate = root / clean_path
    return {
        "path": str(candidate.resolve()) if candidate.exists() else str(candidate),
        "relative_path": rel_path(candidate, root) if candidate.is_absolute() or candidate.exists() else clean,
        "raw": value,
        "exists": candidate.exists(),
    }


def extract_block_image_path(block: dict, root: pathlib.Path) -> dict | None:
    for key in IMAGE_PATH_KEYS:
        value = block.get(key)
        if isinstance(value, str) and looks_like_image_path(value):
            return resolve_image_path(value, root)
    for key in ("image", "img"):
        value = block.get(key)
        if isinstance(value, dict):
            found = extract_block_image_path(value, root)
            if found:
                return found
        if isinstance(value, str) and looks_like_image_path(value):
            return resolve_image_path(value, root)
    return None


def looks_like_image_path(value: str) -> bool:
    path = value.split("?", 1)[0].lower()
    return pathlib.Path(path).suffix in IMAGE_EXTENSIONS or "/images/" in path or path.startswith("images/")


def parse_html_table(html_text: str) -> list[list[str]]:
    rows = []
    for row_match in HTML_ROW_RE.finditer(html_text):
        cells = []
        for cell_match in HTML_CELL_RE.finditer(row_match.group(1)):
            cell_text = TAG_RE.sub("", cell_match.group(1))
            cells.append(html.unescape(cell_text).strip())
        if cells:
            rows.append(cells)
    return rows


def rows_from_table_payload(value: Any) -> list[list[str]] | None:
    if isinstance(value, list):
        rows = []
        for item in value:
            if isinstance(item, list):
                rows.append([str(cell) for cell in item])
            elif isinstance(item, dict):
                row_value = item.get("cells") or item.get("row") or item.get("values")
                if isinstance(row_value, list):
                    rows.append([extract_block_text(cell) or str(cell) for cell in row_value])
        return rows or None
    if isinstance(value, dict):
        for key in ("rows", "table_rows", "table_body", "body", "cells"):
            if key in value:
                rows = rows_from_table_payload(value[key])
                if rows:
                    return rows
    if isinstance(value, str):
        if "<table" in value.lower() or "<tr" in value.lower():
            rows = parse_html_table(value)
            return rows or None
        lines = [line for line in value.splitlines() if is_markdown_table_line(line)]
        if len(lines) >= 2:
            parsed = parse_markdown_table(lines, 1, "table-inline")
            header = parsed.get("headers") or []
            rows = []
            if header:
                rows.append(header)
            for row in parsed["rows"]:
                rows.append([cell["text"] for cell in row["cells"]])
            return rows or None
    return None


def extract_block_table_rows(block: dict) -> list[list[str]] | None:
    for key in ("table_body", "table_rows", "rows", "cells", "table"):
        if key in block:
            rows = rows_from_table_payload(block[key])
            if rows:
                return rows
    text = extract_block_text(block)
    if text:
        return rows_from_table_payload(text)
    return None


def normalize_content_block(block: dict, source_file: pathlib.Path, block_index: int, root: pathlib.Path, args: argparse.Namespace) -> dict:
    text = extract_block_text(block)
    page, page_index = extract_block_page(block)
    label = extract_label(text or "")
    block_type = classify_content_block(block)
    content_ref = {
        "source_file": str(source_file),
        "relative_source_file": rel_path(source_file, root),
        "block_index": block_index,
        "block_id": stable_id("content", block_index + 1),
        "raw_type": raw_type(block),
    }
    return {
        "id": stable_id("content", block_index + 1),
        "type": block_type,
        "text": truncate_text(text, args.max_context_chars) if text else None,
        "full_text": text,
        "label": label["label"] if label else None,
        "label_kind": label["kind"] if label else None,
        "label_key": label["key"] if label else None,
        "page": page,
        "page_index": page_index,
        "bbox": extract_block_bbox(block, "content_list"),
        "image_ref": extract_block_image_path(block, root),
        "table_rows": extract_block_table_rows(block),
        "content_ref": content_ref,
        "provenance": {
            "sources": ["content_list"],
            "confidence": "medium",
            "raw": raw_for_output(block, args.include_raw, args.max_context_chars),
        },
    }


def walk_json(value: Any, path: tuple[Any, ...] = ()) -> Iterable[tuple[tuple[Any, ...], Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk_json(item, path + (key,))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            yield from walk_json(item, path + (idx,))


def json_path(path: tuple[Any, ...]) -> list[Any]:
    return list(path)


def likely_page_node(node: dict) -> bool:
    has_page_key = any(key in node for key in PAGE_KEYS + PAGE_INDEX_KEYS)
    has_blocks = any(isinstance(node.get(key), list) for key in MIDDLE_BLOCK_KEYS)
    has_size = any(key in node for key in ("width", "height", "w", "h", "page_size"))
    return has_page_key and (has_blocks or has_size)


def page_size(node: dict) -> tuple[Any | None, Any | None]:
    width = node.get("width", node.get("w"))
    height = node.get("height", node.get("h"))
    size = node.get("page_size")
    if isinstance(size, list) and len(size) >= 2:
        width = width if width is not None else size[0]
        height = height if height is not None else size[1]
    if isinstance(size, dict):
        width = width if width is not None else size.get("width") or size.get("w")
        height = height if height is not None else size.get("height") or size.get("h")
    return width, height


def find_page_nodes(data: Any, source_file: pathlib.Path, root: pathlib.Path, args: argparse.Namespace) -> list[dict]:
    pages = []
    seen = set()
    for path, node in walk_json(data):
        if not isinstance(node, dict) or not likely_page_node(node):
            continue
        page, page_index = extract_block_page(node)
        key = (page, page_index, path)
        if key in seen:
            continue
        seen.add(key)
        width, height = page_size(node)
        pages.append(
            {
                "id": short_id("page", len(pages) + 1),
                "page": page,
                "page_index": page_index,
                "width": width,
                "height": height,
                "middle_ref": {
                    "source_file": str(source_file),
                    "relative_source_file": rel_path(source_file, root),
                    "json_path": json_path(path),
                },
                "provenance": {
                    "sources": ["middle"],
                    "confidence": "medium",
                    "raw": raw_for_output(node, args.include_raw, args.max_context_chars),
                },
            }
        )
    return pages


def iter_middle_blocks(data: Any) -> Iterable[tuple[tuple[Any, ...], dict, tuple[int | None, int | None] | None]]:
    for path, node in walk_json(data):
        if not isinstance(node, dict):
            continue
        parent_page = extract_block_page(node) if likely_page_node(node) else None
        for key in MIDDLE_BLOCK_KEYS:
            value = node.get(key)
            if not isinstance(value, list):
                continue
            for idx, child in enumerate(value):
                if isinstance(child, dict):
                    yield path + (key, idx), child, parent_page


def normalize_middle_block(
    block: dict,
    source_file: pathlib.Path,
    block_index: int,
    raw_path: tuple[Any, ...],
    parent_page: tuple[int | None, int | None] | None,
    root: pathlib.Path,
    args: argparse.Namespace,
) -> dict:
    text = extract_block_text(block)
    page, page_index = extract_block_page(block, parent_page)
    label = extract_label(text or "")
    block_type = classify_content_block(block)
    middle_ref = {
        "source_file": str(source_file),
        "relative_source_file": rel_path(source_file, root),
        "json_path": json_path(raw_path),
        "block_index": block_index,
        "raw_type": raw_type(block),
    }
    return {
        "id": stable_id("middle", block_index + 1),
        "type": block_type,
        "text": truncate_text(text, args.max_context_chars) if text else None,
        "full_text": text,
        "label": label["label"] if label else None,
        "label_kind": label["kind"] if label else None,
        "label_key": label["key"] if label else None,
        "page": page,
        "page_index": page_index,
        "bbox": extract_block_bbox(block, "middle"),
        "image_ref": extract_block_image_path(block, root),
        "table_rows": extract_block_table_rows(block),
        "middle_ref": middle_ref,
        "provenance": {
            "sources": ["middle"],
            "confidence": "medium",
            "raw": raw_for_output(block, args.include_raw, args.max_context_chars),
        },
    }


def extract_label(text: str | None) -> dict | None:
    if not text:
        return None
    stripped = text.strip()
    match = EN_LABEL_RE.search(stripped)
    if match:
        kind_raw = match.group("kind")
        number = match.group("num")
        kind = "table" if kind_raw.lower().startswith("table") else "figure"
        display = f"Table {number}" if kind == "table" else f"Figure {number}"
        raw_label = match.group(0).strip()
        return {"kind": kind, "label": display, "raw_label": raw_label, "number": number, "key": label_key(display)}
    match = CN_LABEL_RE.search(stripped)
    if match:
        kind_raw = match.group("kind")
        number = match.group("num")
        kind = "table" if kind_raw == "表" else "figure"
        display = f"{kind_raw}{number}"
        raw_label = match.group(0).strip()
        return {"kind": kind, "label": display, "raw_label": raw_label, "number": number, "key": label_key(display)}
    return None


def label_key(label: str | None) -> str | None:
    if not label:
        return None
    return re.sub(r"[^a-z0-9一-龥]+", "", label.lower())


def index_image_files(images_dir: pathlib.Path | None, root: pathlib.Path, hash_images: bool) -> list[dict]:
    if images_dir is None or not images_dir.exists():
        return []
    images = []
    for path in sorted(item for item in images_dir.rglob("*") if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS):
        sha256 = None
        if hash_images:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            sha256 = digest.hexdigest()
        images.append(
            {
                "id": short_id("image", len(images) + 1),
                "type": "image",
                "path": str(path.resolve()),
                "relative_path": rel_path(path, root),
                "file_name": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256,
                "linked_items": [],
            }
        )
    return images


def match_image_refs(records: list[dict], images: list[dict], warnings: list[dict]) -> None:
    by_rel = {image["relative_path"]: image for image in images}
    by_name: dict[str, list[dict]] = collections.defaultdict(list)
    for image in images:
        by_name[image["file_name"]].append(image)
    for record in records:
        image_ref = record.get("image_ref")
        if not image_ref:
            continue
        rel = image_ref.get("relative_path")
        raw = image_ref.get("raw") or rel
        matched = by_rel.get(rel)
        if matched is None and raw:
            matches = by_name.get(pathlib.Path(str(raw)).name, [])
            if len(matches) == 1:
                matched = matches[0]
            elif len(matches) > 1:
                add_warning(warnings, "image_match_ambiguous", "Image reference matched multiple files by basename", reference=str(raw), matches=[item["relative_path"] for item in matches])
        if matched is None:
            if raw:
                add_warning(warnings, "image_reference_unresolved", "Could not resolve image reference", reference=str(raw), record_id=record.get("id"))
            continue
        image_ref["image_id"] = matched["id"]
        if record.get("id") not in matched["linked_items"]:
            matched["linked_items"].append(record.get("id"))


def table_from_rows(
    table_id: str,
    source: str,
    rows: list[list[str]],
    first_row_is_header: bool = True,
    markdown_ref: dict | None = None,
    content_ref: dict | None = None,
    middle_ref: dict | None = None,
    page: int | None = None,
    page_index: int | None = None,
    bbox: dict | None = None,
    image_ref: dict | None = None,
    label: str | None = None,
    label_key_value: str | None = None,
    text: str | None = None,
    provenance: dict | None = None,
) -> tuple[dict, list[dict]]:
    headers: list[str] = []
    data_rows = rows
    if rows and first_row_is_header:
        headers = [str(cell).strip() for cell in rows[0]]
        data_rows = rows[1:] if len(rows) > 1 else []
    cells = []
    normalized_rows = []
    for row_index, row in enumerate(data_rows, start=1):
        row_cells = []
        row_label = str(row[0]).strip() if row else None
        for column_index, value in enumerate(row, start=1):
            cell_id = f"cell-{table_id}-r{row_index:03d}-c{column_index:03d}"
            column_label = headers[column_index - 1] if column_index <= len(headers) else None
            cell = {
                "id": cell_id,
                "type": "table_cell",
                "table_id": table_id,
                "source": source,
                "page": page,
                "page_index": page_index,
                "row_index": row_index,
                "column_index": column_index,
                "row_label": row_label,
                "column_label": column_label,
                "text": str(value).strip(),
                "original_value": str(value),
                "markdown_ref": markdown_ref,
                "content_ref": content_ref,
                "middle_ref": middle_ref,
                "bbox": None,
                "provenance": provenance or {"sources": [source], "confidence": "medium"},
            }
            cells.append(cell)
            row_cells.append(cell_id)
        normalized_rows.append({"row_index": row_index, "row_label": row_label, "cells": row_cells})
    table = {
        "id": table_id,
        "type": "table",
        "source": source,
        "label": label,
        "label_key": label_key_value or label_key(label),
        "text": text,
        "page": page,
        "page_index": page_index,
        "bbox": bbox,
        "markdown_ref": markdown_ref,
        "content_ref": content_ref,
        "middle_ref": middle_ref,
        "image_ref": image_ref,
        "headers": headers,
        "rows": normalized_rows,
        "cells": [cell["id"] for cell in cells],
        "caption_id": None,
        "caption_text": None,
        "related_items": [],
        "provenance": provenance or {"sources": [source], "confidence": "medium"},
    }
    return table, cells


def build_tables_from_markdown(md_tables: list[dict], md_path: pathlib.Path | None, root: pathlib.Path) -> tuple[list[dict], list[dict]]:
    tables = []
    cells = []
    for table in md_tables:
        rows = []
        if table.get("headers"):
            rows.append(table["headers"])
        for row in table["rows"]:
            rows.append([cell["original_value"] for cell in row["cells"]])
        markdown_ref = None
        if md_path:
            markdown_ref = {
                "path": str(md_path),
                "relative_path": rel_path(md_path, root),
                "line_start": table["start_line"],
                "line_end": table["end_line"],
            }
        normalized, table_cells = table_from_rows(
            table["id"],
            "markdown",
            rows,
            first_row_is_header=bool(table.get("headers")),
            markdown_ref=markdown_ref,
            provenance={"sources": ["markdown"], "confidence": "high"},
        )
        normalized["raw_lines"] = table["raw_lines"]
        tables.append(normalized)
        cells.extend(table_cells)
    return tables, cells


def build_tables_from_blocks(blocks: list[dict], source: str) -> tuple[list[dict], list[dict]]:
    tables = []
    cells = []
    counter = 0
    for block in blocks:
        if block.get("type") != "table":
            continue
        counter += 1
        table_id = short_id(f"table-{source}", counter)
        rows = block.get("table_rows") or []
        if rows:
            table, table_cells = table_from_rows(
                table_id,
                source,
                rows,
                content_ref=block.get("content_ref"),
                middle_ref=block.get("middle_ref"),
                page=block.get("page"),
                page_index=block.get("page_index"),
                bbox=block.get("bbox"),
                image_ref=block.get("image_ref"),
                label=block.get("label"),
                label_key_value=block.get("label_key"),
                text=block.get("text"),
                provenance=block.get("provenance"),
            )
        else:
            table = {
                "id": table_id,
                "type": "table",
                "source": source,
                "label": block.get("label"),
                "label_key": block.get("label_key"),
                "text": block.get("text"),
                "page": block.get("page"),
                "page_index": block.get("page_index"),
                "bbox": block.get("bbox"),
                "markdown_ref": None,
                "content_ref": block.get("content_ref"),
                "middle_ref": block.get("middle_ref"),
                "image_ref": block.get("image_ref"),
                "headers": [],
                "rows": [],
                "cells": [],
                "caption_id": None,
                "caption_text": None,
                "related_items": [block.get("id")],
                "provenance": block.get("provenance"),
            }
            table_cells = []
        tables.append(table)
        cells.extend(table_cells)
    return tables, cells


def captions_from_blocks(blocks: list[dict], source: str) -> list[dict]:
    captions = []
    for block in blocks:
        text = block.get("full_text") or block.get("text")
        label = extract_label(text or "")
        if block.get("type") != "caption" and not label:
            continue
        captions.append(
            {
                "id": short_id(f"caption-{source}", len(captions) + 1),
                "type": "caption",
                "source": source,
                "text": text,
                "label": label["label"] if label else block.get("label"),
                "label_kind": label["kind"] if label else block.get("label_kind"),
                "label_key": label["key"] if label else block.get("label_key"),
                "raw_label": label["raw_label"] if label else None,
                "page": block.get("page"),
                "page_index": block.get("page_index"),
                "bbox": block.get("bbox"),
                "markdown_ref": block.get("markdown_ref"),
                "content_ref": block.get("content_ref"),
                "middle_ref": block.get("middle_ref"),
                "caption_for": None,
                "link_confidence": None,
                "provenance": block.get("provenance"),
            }
        )
    return captions


def figures_from_markdown_refs(refs: list[dict]) -> list[dict]:
    figures = []
    for ref in refs:
        label = extract_label(ref.get("alt_text") or "")
        figures.append(
            {
                "id": short_id("figure-md", len(figures) + 1),
                "type": "figure",
                "source": "markdown",
                "label": label["label"] if label else None,
                "label_key": label["key"] if label else None,
                "alt_text": ref.get("alt_text"),
                "text": ref.get("alt_text"),
                "page": None,
                "page_index": None,
                "bbox": None,
                "image_ref": ref.get("image_ref"),
                "markdown_ref": ref.get("markdown_ref"),
                "content_ref": None,
                "middle_ref": None,
                "caption_id": None,
                "caption_text": None,
                "related_items": [ref.get("id")],
                "provenance": {"sources": ["markdown"], "confidence": "medium"},
            }
        )
    return figures


def figures_from_blocks(blocks: list[dict], source: str) -> list[dict]:
    figures = []
    for block in blocks:
        if block.get("type") not in {"figure", "image"} and not block.get("image_ref"):
            continue
        figures.append(
            {
                "id": short_id(f"figure-{source}", len(figures) + 1),
                "type": "figure",
                "source": source,
                "label": block.get("label"),
                "label_key": block.get("label_key"),
                "text": block.get("full_text") or block.get("text"),
                "page": block.get("page"),
                "page_index": block.get("page_index"),
                "bbox": block.get("bbox"),
                "image_ref": block.get("image_ref"),
                "markdown_ref": None,
                "content_ref": block.get("content_ref"),
                "middle_ref": block.get("middle_ref"),
                "caption_id": None,
                "caption_text": None,
                "related_items": [block.get("id")],
                "provenance": block.get("provenance"),
            }
        )
    return figures


def link_captions(captions: list[dict], figures: list[dict], tables: list[dict]) -> None:
    candidates = figures + tables
    by_key: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for candidate in candidates:
        key = candidate.get("label_key")
        if key:
            by_key[(candidate["type"], key)].append(candidate)
    for caption in captions:
        kind = caption.get("label_kind")
        key = caption.get("label_key")
        if not kind or not key:
            continue
        matches = by_key.get((kind, key), [])
        if len(matches) == 1:
            attach_caption(caption, matches[0], "high")
    for caption in captions:
        if caption.get("caption_for"):
            continue
        kind = caption.get("label_kind")
        if kind not in {"figure", "table"}:
            continue
        pool = figures if kind == "figure" else tables
        same_page = [item for item in pool if item.get("caption_id") is None and item.get("page") == caption.get("page") and item.get("page") is not None]
        if len(same_page) == 1:
            if not same_page[0].get("label") and caption.get("label"):
                same_page[0]["label"] = caption["label"]
                same_page[0]["label_key"] = caption.get("label_key")
            attach_caption(caption, same_page[0], "medium")


def attach_caption(caption: dict, item: dict, confidence: str) -> None:
    caption["caption_for"] = item.get("id")
    caption["link_confidence"] = confidence
    item["caption_id"] = caption.get("id")
    item["caption_text"] = caption.get("text")
    if not item.get("label") and caption.get("label"):
        item["label"] = caption.get("label")
        item["label_key"] = caption.get("label_key")


def collect_pages(existing_pages: list[dict], records: list[dict]) -> list[dict]:
    pages = list(existing_pages)
    seen = {(page.get("page"), page.get("page_index")) for page in pages}
    values = sorted({(record.get("page"), record.get("page_index")) for record in records if record.get("page") is not None or record.get("page_index") is not None})
    for page, page_index in values:
        key = (page, page_index)
        if key in seen:
            continue
        pages.append(
            {
                "id": short_id("page", len(pages) + 1),
                "page": page,
                "page_index": page_index,
                "width": None,
                "height": None,
                "middle_ref": None,
                "provenance": {"sources": ["derived"], "confidence": "low"},
            }
        )
        seen.add(key)
    return pages


def make_markdown_line_item(record: dict, counter: int) -> dict:
    return {
        "id": stable_id("ev", counter),
        "type": "markdown_line",
        "subtype": record.get("kind_hint"),
        "source_item_id": record.get("id"),
        "text": record.get("text"),
        "original_value": record.get("text"),
        "page": None,
        "page_index": None,
        "bbox": None,
        "markdown_ref": record.get("markdown_ref"),
        "content_ref": None,
        "middle_ref": None,
        "image_ref": None,
        "table_ref": None,
        "figure_ref": None,
        "related_items": [],
        "provenance": {"sources": ["markdown"], "confidence": "high"},
    }


def make_generic_item(record: dict, counter: int, item_type: str | None = None) -> dict:
    record_type = item_type or record.get("type") or "unknown"
    return {
        "id": stable_id("ev", counter),
        "type": record_type,
        "subtype": record.get("source"),
        "source_item_id": record.get("id"),
        "label": record.get("label"),
        "text": record.get("text") or record.get("full_text"),
        "original_value": record.get("original_value") or record.get("text") or record.get("full_text"),
        "page": record.get("page"),
        "page_index": record.get("page_index"),
        "bbox": record.get("bbox"),
        "markdown_ref": record.get("markdown_ref"),
        "content_ref": record.get("content_ref"),
        "middle_ref": record.get("middle_ref"),
        "image_ref": record.get("image_ref") or image_ref_from_image_record(record),
        "table_ref": table_ref_from_record(record),
        "figure_ref": figure_ref_from_record(record),
        "related_items": record.get("related_items", []),
        "provenance": record.get("provenance"),
    }


def image_ref_from_image_record(record: dict) -> dict | None:
    if record.get("type") != "image":
        return None
    return {
        "path": record.get("path"),
        "relative_path": record.get("relative_path"),
        "sha256": record.get("sha256"),
        "image_id": record.get("id"),
    }


def table_ref_from_record(record: dict) -> dict | None:
    if record.get("type") == "table":
        return {
            "table_id": record.get("id"),
            "table_number": record.get("label"),
            "row_index": None,
            "row_label": None,
            "column_index": None,
            "column_label": None,
            "cell_id": None,
        }
    if record.get("type") == "table_cell":
        return {
            "table_id": record.get("table_id"),
            "table_number": None,
            "row_index": record.get("row_index"),
            "row_label": record.get("row_label"),
            "column_index": record.get("column_index"),
            "column_label": record.get("column_label"),
            "cell_id": record.get("id"),
        }
    return None


def figure_ref_from_record(record: dict) -> dict | None:
    if record.get("type") != "figure":
        return None
    return {
        "figure_id": record.get("id"),
        "figure_number": record.get("label"),
        "caption_id": record.get("caption_id"),
    }


def build_ledger_items(markdown_lines: list[dict], records: list[dict]) -> list[dict]:
    items = []
    counter = 1
    for line in markdown_lines:
        items.append(make_markdown_line_item(line, counter))
        counter += 1
    for record in records:
        items.append(make_generic_item(record, counter))
        counter += 1
    return items


def build_indexes(items: list[dict]) -> dict:
    indexes = {
        "by_type": collections.defaultdict(list),
        "by_page": collections.defaultdict(list),
        "by_image_path": collections.defaultdict(list),
        "by_markdown_line": collections.defaultdict(list),
        "by_table_label": collections.defaultdict(list),
        "by_figure_label": collections.defaultdict(list),
    }
    for item in items:
        item_id = item["id"]
        indexes["by_type"][item.get("type") or "unknown"].append(item_id)
        if item.get("page") is not None:
            indexes["by_page"][str(item["page"])].append(item_id)
        image_ref = item.get("image_ref") or {}
        if image_ref.get("relative_path"):
            indexes["by_image_path"][image_ref["relative_path"]].append(item_id)
        markdown_ref = item.get("markdown_ref") or {}
        line_start = markdown_ref.get("line_start")
        line_end = markdown_ref.get("line_end") or line_start
        if line_start is not None:
            for line in range(int(line_start), int(line_end) + 1):
                indexes["by_markdown_line"][str(line)].append(item_id)
        table_ref = item.get("table_ref") or {}
        if table_ref.get("table_number"):
            indexes["by_table_label"][table_ref["table_number"]].append(item_id)
        figure_ref = item.get("figure_ref") or {}
        if figure_ref.get("figure_number"):
            indexes["by_figure_label"][figure_ref["figure_number"]].append(item_id)
    return {key: dict(value) for key, value in indexes.items()}


def warning_if_missing_files(md_path: pathlib.Path | None, content_files: list[pathlib.Path], middle_files: list[pathlib.Path], images_dir: pathlib.Path | None, warnings: list[dict]) -> None:
    if md_path is None:
        add_warning(warnings, "markdown_missing", "No full.md or markdown file was found")
    if not content_files:
        add_warning(warnings, "content_list_missing", "No *_content_list.json files were found")
    if not middle_files:
        add_warning(warnings, "middle_json_missing", "No *_middle.json files were found")
    if images_dir is None:
        add_warning(warnings, "images_dir_missing", "No images directory was found")


def build_source(root: pathlib.Path, manifest: dict | None, manifest_path: pathlib.Path | None, md_path: pathlib.Path | None, content_files: list[pathlib.Path], middle_files: list[pathlib.Path], images_dir: pathlib.Path | None) -> dict:
    return {
        "mineru_output_dir": str(root),
        "manifest_path": str(manifest_path) if manifest_path else None,
        "manifest": manifest,
        "files": {
            "markdown": str(md_path) if md_path else None,
            "content_list": [str(path) for path in content_files],
            "middle": [str(path) for path in middle_files],
            "images_dir": str(images_dir) if images_dir else None,
        },
        "relative_files": {
            "markdown": rel_path(md_path, root) if md_path else None,
            "content_list": [rel_path(path, root) for path in content_files],
            "middle": [rel_path(path, root) for path in middle_files],
            "images_dir": rel_path(images_dir, root) if images_dir else None,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a unified evidence ledger from MinerU output files.")
    parser.add_argument("input", help="MinerU output directory.")
    parser.add_argument("--output", required=True, help="JSON output path.")
    parser.add_argument("--include-raw", choices=["none", "summary", "full"], default="summary")
    parser.add_argument("--max-context-chars", type=int, default=500)
    parser.add_argument("--image-hash", action="store_true", help="Compute SHA-256 hashes for extracted images.")
    parser.add_argument("--strict", action="store_true", help="Fail on malformed expected JSON files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = pathlib.Path(args.input).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    output = pathlib.Path(args.output).expanduser().resolve()

    warnings: list[dict] = []
    manifest, manifest_path = load_manifest(root, warnings, args.strict)
    md_path = find_full_md(root)
    content_files = find_content_list_files(root)
    middle_files = find_middle_files(root)
    images_dir = find_images_dir(root)
    warning_if_missing_files(md_path, content_files, middle_files, images_dir, warnings)

    markdown_lines: list[dict] = []
    markdown_tables: list[dict] = []
    markdown_image_refs: list[dict] = []
    captions: list[dict] = []
    if md_path:
        markdown_lines = read_markdown_lines(md_path, root, args.max_context_chars)
        markdown_tables = extract_markdown_tables(markdown_lines)
        markdown_image_refs = find_markdown_image_refs(markdown_lines, root)
        captions.extend(find_caption_like_lines(markdown_lines))

    content_blocks: list[dict] = []
    for content_file in content_files:
        data = load_json_file(content_file, warnings, args.strict)
        if data is None:
            continue
        for block_index, block, _container_key in iter_content_blocks(data, content_file, warnings):
            content_blocks.append(normalize_content_block(block, content_file, len(content_blocks), root, args))

    middle_blocks: list[dict] = []
    pages: list[dict] = []
    for middle_file in middle_files:
        data = load_json_file(middle_file, warnings, args.strict)
        if data is None:
            continue
        pages.extend(find_page_nodes(data, middle_file, root, args))
        before_count = len(middle_blocks)
        for raw_path, block, parent_page in iter_middle_blocks(data):
            middle_blocks.append(normalize_middle_block(block, middle_file, len(middle_blocks), raw_path, parent_page, root, args))
        if len(middle_blocks) == before_count:
            add_warning(warnings, "middle_blocks_not_found", "No block arrays were found in middle JSON", path=str(middle_file))

    images = index_image_files(images_dir, root, args.image_hash)

    markdown_table_records, markdown_cells = build_tables_from_markdown(markdown_tables, md_path, root)
    content_table_records, content_cells = build_tables_from_blocks(content_blocks, "content")
    middle_table_records, middle_cells = build_tables_from_blocks(middle_blocks, "middle")
    tables = markdown_table_records + content_table_records + middle_table_records
    cells = markdown_cells + content_cells + middle_cells

    captions.extend(captions_from_blocks(content_blocks, "content"))
    captions.extend(captions_from_blocks(middle_blocks, "middle"))

    figures = figures_from_markdown_refs(markdown_image_refs)
    figures.extend(figures_from_blocks(content_blocks, "content"))
    figures.extend(figures_from_blocks(middle_blocks, "middle"))

    match_image_refs(figures + tables + content_blocks + middle_blocks, images, warnings)
    link_captions(captions, figures, tables)

    pages = collect_pages(pages, content_blocks + middle_blocks + figures + tables + captions)

    item_records = pages + content_blocks + middle_blocks + captions + figures + images + tables + cells
    ledger_items = build_ledger_items(markdown_lines, item_records)
    indexes = build_indexes(ledger_items)

    stats = {
        "markdown_lines": len(markdown_lines),
        "content_blocks": len(content_blocks),
        "middle_blocks": len(middle_blocks),
        "pages": len(pages),
        "tables": len(tables),
        "figures": len(figures),
        "images": len(images),
        "captions": len(captions),
        "cells": len(cells),
        "ledger_items": len(ledger_items),
        "warnings": len(warnings),
    }

    ledger = {
        "schema_version": "1.0",
        "created_by": "build_evidence_ledger.py",
        "created_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": build_source(root, manifest, manifest_path, md_path, content_files, middle_files, images_dir),
        "warnings": warnings,
        "stats": stats,
        "indexes": indexes,
        "markdown": {
            "path": str(md_path) if md_path else None,
            "relative_path": rel_path(md_path, root) if md_path else None,
            "line_count": len(markdown_lines),
            "lines": markdown_lines,
            "image_refs": markdown_image_refs,
            "caption_lines": [caption for caption in captions if caption.get("source") == "markdown"],
            "tables": markdown_tables,
        },
        "content_blocks": content_blocks,
        "middle_blocks": middle_blocks,
        "pages": pages,
        "tables": tables,
        "figures": figures,
        "images": images,
        "captions": captions,
        "cells": cells,
        "ledger_items": ledger_items,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), **stats}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
