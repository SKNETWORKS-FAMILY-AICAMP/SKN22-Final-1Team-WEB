from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import fitz

from app.services.storage_service import persist_named_asset_reference, resolve_storage_reference


CHATBOT_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "chatbot"
NCS_SOURCE_DIR = Path(__file__).resolve().parents[3] / "data" / "rag" / "sources" / "ncs"
EXPECTED_IMAGE_MANIFEST_PATH = CHATBOT_DATA_DIR / "ncs_expected_question_images.json"

EMBEDDED_IMAGE_MIN_WIDTH = 80
EMBEDDED_IMAGE_MIN_HEIGHT = 80


def _normalize_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


@lru_cache(maxsize=1)
def _load_manifest() -> list[dict[str, Any]]:
    if not EXPECTED_IMAGE_MANIFEST_PATH.exists():
        return []
    try:
        payload = json.loads(EXPECTED_IMAGE_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


@lru_cache(maxsize=1)
def _pdf_path_lookup() -> dict[str, Path]:
    lookup: dict[str, Path] = {}
    if not NCS_SOURCE_DIR.exists():
        return lookup
    for path in NCS_SOURCE_DIR.glob("*.pdf"):
        lookup[unicodedata.normalize("NFC", path.name)] = path
    return lookup


@lru_cache(maxsize=8)
def _open_pdf(pdf_name: str) -> fitz.Document:
    lookup = _pdf_path_lookup()
    pdf_path = lookup.get(unicodedata.normalize("NFC", pdf_name))
    if pdf_path is None:
        raise FileNotFoundError(f"PDF not found: {pdf_name}")
    return fitz.open(pdf_path)


def get_expected_question_image_catalog() -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for entry in _load_manifest():
        source_pdf = str(entry.get("source_pdf") or "").strip()
        items = [
            {
                "id": item.get("id"),
                "page": item.get("page"),
                "figure": item.get("figure"),
                "title": item.get("title"),
                "caption": item.get("caption"),
                "extract_strategy": item.get("extract_strategy") or "page",
                "max_images": item.get("max_images"),
            }
            for item in entry.get("items") or []
            if isinstance(item, dict)
        ]
        catalog.append(
            {
                "id": entry.get("id"),
                "question_label": entry.get("question_label"),
                "match_keywords": list(entry.get("match_keywords") or []),
                "source_pdf": source_pdf,
                "source_pdf_path": str(_pdf_path_lookup().get(unicodedata.normalize("NFC", source_pdf)) or ""),
                "items": items,
            }
        )
    return catalog


def _match_manifest_entries(question: str) -> list[dict[str, Any]]:
    normalized_question = _normalize_text(question)
    if not normalized_question:
        return []

    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for index, entry in enumerate(_load_manifest()):
        keywords = [_normalize_text(keyword) for keyword in entry.get("match_keywords") or [] if keyword]
        score = sum(1 for keyword in keywords if keyword and keyword in normalized_question)
        if score > 0:
            ranked.append((score, -index, entry))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [entry for _, _, entry in ranked]


def _candidate_embedded_images(page: fitz.Page, *, max_images: int | None = None) -> list[tuple[int, fitz.Rect]]:
    seen: set[tuple[int, int, int]] = set()
    candidates: list[tuple[int, fitz.Rect]] = []
    for image in page.get_images(full=True):
        xref = int(image[0])
        rects = page.get_image_rects(xref)
        if not rects:
            continue
        rect = rects[0]
        width = float(rect.width)
        height = float(rect.height)
        if width < EMBEDDED_IMAGE_MIN_WIDTH or height < EMBEDDED_IMAGE_MIN_HEIGHT:
            continue
        key = (xref, int(round(width)), int(round(height)))
        if key in seen:
            continue
        seen.add(key)
        candidates.append((xref, rect))

    candidates.sort(key=lambda item: (round(item[1].y0, 1), round(item[1].x0, 1)))
    if max_images is not None:
        return candidates[: max(1, max_images)]
    return candidates


def _extract_embedded_image(doc: fitz.Document, *, xref: int) -> tuple[bytes, str]:
    extracted = doc.extract_image(xref)
    image_bytes = extracted.get("image") if isinstance(extracted, dict) else None
    extension = str((extracted or {}).get("ext") or "png").lower()

    if image_bytes and extension in {"png", "jpg", "jpeg", "webp"}:
        mime_type = "image/jpeg" if extension in {"jpg", "jpeg"} else f"image/{extension}"
        return image_bytes, mime_type

    pixmap = fitz.Pixmap(doc, xref)
    return pixmap.tobytes("png"), "image/png"


def _render_page_preview(doc: fitz.Document, *, page_number: int) -> tuple[bytes, str]:
    page = doc[page_number - 1]
    pixmap = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
    return pixmap.tobytes("png"), "image/png"


def _persist_visual_bytes(
    *,
    asset_bytes: bytes,
    mime_type: str,
    entry_id: str,
    item_id: str,
    filename: str,
) -> str | None:
    relative_path = f"chatbot/ncs/{entry_id}/{item_id}/{filename}"
    return persist_named_asset_reference(
        asset_bytes,
        relative_path=relative_path,
        mime_type=mime_type,
    )


def _resolve_item_images(
    entry: dict[str, Any],
    item: dict[str, Any],
) -> list[dict[str, Any]]:
    entry_id = str(entry.get("id") or "expected-question").strip() or "expected-question"
    item_id = str(item.get("id") or f"page-{item.get('page')}").strip() or f"page-{item.get('page')}"
    source_pdf = str(entry.get("source_pdf") or "").strip()
    page_number = int(item.get("page") or 0)
    if not source_pdf or page_number <= 0:
        return []

    doc = _open_pdf(source_pdf)
    if page_number > len(doc):
        return []

    page = doc[page_number - 1]
    extract_strategy = str(item.get("extract_strategy") or "page").strip().lower()
    max_images = int(item.get("max_images") or 0) or None

    results: list[dict[str, Any]] = []
    if extract_strategy == "embedded":
        for order, (xref, _) in enumerate(_candidate_embedded_images(page, max_images=max_images), start=1):
            image_bytes, mime_type = _extract_embedded_image(doc, xref=xref)
            extension = ".jpg" if mime_type == "image/jpeg" else ".png"
            reference = _persist_visual_bytes(
                asset_bytes=image_bytes,
                mime_type=mime_type,
                entry_id=entry_id,
                item_id=item_id,
                filename=f"img-{order:02d}{extension}",
            )
            if not reference:
                continue
            title = str(item.get("title") or entry.get("question_label") or "NCS 참고 이미지").strip()
            if max_images is None or max_images > 1:
                title = f"{title} {order}"
            results.append(
                {
                    "id": f"{item_id}-{order:02d}",
                    "title": title,
                    "caption": str(item.get("caption") or "").strip(),
                    "figure": str(item.get("figure") or "").strip(),
                    "source_pdf": source_pdf,
                    "page": page_number,
                    "reference": reference,
                    "url": resolve_storage_reference(reference),
                }
            )
        if results:
            return results

    image_bytes, mime_type = _render_page_preview(doc, page_number=page_number)
    reference = _persist_visual_bytes(
        asset_bytes=image_bytes,
        mime_type=mime_type,
        entry_id=entry_id,
        item_id=item_id,
        filename=f"page-{page_number:03d}.png",
    )
    if not reference:
        return []
    return [
        {
            "id": item_id,
            "title": str(item.get("title") or entry.get("question_label") or "NCS 참고 페이지").strip(),
            "caption": str(item.get("caption") or "").strip(),
            "figure": str(item.get("figure") or "").strip(),
            "source_pdf": source_pdf,
            "page": page_number,
            "reference": reference,
            "url": resolve_storage_reference(reference),
        }
    ]


def resolve_expected_question_images(question: str, *, max_entries: int = 2) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    for entry in _match_manifest_entries(question)[: max(1, max_entries)]:
        for item in entry.get("items") or []:
            if not isinstance(item, dict):
                continue
            images.extend(_resolve_item_images(entry, item))
    return [image for image in images if image.get("url")]
