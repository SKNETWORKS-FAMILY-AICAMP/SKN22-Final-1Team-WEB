from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from typing import Any

import chromadb
from chromadb.errors import NotFoundError

from .chroma_client import create_persistent_client
from .paths import CHROMA_TRENDS_DIR, TREND_PROCESSED_DIR, ensure_directories
from .rag_safety import sanitize_rag_items


INPUT_FILE = TREND_PROCESSED_DIR / "final_rag_trends.json"
FALLBACK_INPUT_FILE = TREND_PROCESSED_DIR / "refined_trends.json"
TRANSLATION_CACHE_FILE = TREND_PROCESSED_DIR / "latest_trend_translations.json"
COLLECTION_NAME = "hair_trends"
ARTICLE_MATCH_SCORE_THRESHOLD = 35
ARTICLE_MATCH_OVERLAP_THRESHOLD = 2


def load_data() -> list[dict[str, Any]]:
    if INPUT_FILE.exists():
        with INPUT_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            raise ValueError(f"Invalid JSON structure: {INPUT_FILE}")
        sanitized, report = sanitize_rag_items([item for item in data if isinstance(item, dict)])
        enriched = _merge_refined_metadata(sanitized)
        localized = _attach_korean_localizations(enriched)
        _print_safety_report(report)
        return localized

    if not FALLBACK_INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE} or {FALLBACK_INPUT_FILE}")

    with FALLBACK_INPUT_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(f"Invalid JSON structure: {FALLBACK_INPUT_FILE}")

    normalized = [_normalize_refined_item(item) for item in data if isinstance(item, dict)]
    sanitized, report = sanitize_rag_items(normalized)
    localized = _attach_korean_localizations(sanitized)
    _print_safety_report(report)
    return localized


def _normalize_refined_item(item: dict[str, Any]) -> dict[str, Any]:
    title = str(item.get("trend_name", "")).strip()
    description = str(item.get("description", "")).strip()
    style_tags = _split_csv(item.get("hairstyle_text", ""))
    color_tags = _split_csv(item.get("color_text", ""))
    article_title = str(item.get("article_title", "")).strip()
    article_url = str(item.get("article_url", "")).strip()
    image_url = str(item.get("image_url", "")).strip()
    published_at = str(item.get("published_at", "")).strip()
    crawled_at = str(item.get("crawled_at", "")).strip()

    category = "style_trend"
    if color_tags and not style_tags:
        category = "color_trend"
    elif _looks_like_guide(title, description):
        category = "styling_guide"

    canonical_name = _slugify(title or "trend")
    search_chunks = [title, description]
    if style_tags:
        search_chunks.append("styles: " + ", ".join(style_tags))
    if color_tags:
        search_chunks.append("colors: " + ", ".join(color_tags))

    return {
        "canonical_name": canonical_name,
        "display_title": title,
        "category": category,
        "style_tags": style_tags,
        "color_tags": color_tags,
        "summary": description[:400],
        "search_text": "\n".join(chunk for chunk in search_chunks if chunk),
        "source": item.get("source", ""),
        "year": str(item.get("year", "")),
        "article_title": article_title,
        "article_url": article_url,
        "image_url": image_url,
        "published_at": published_at,
        "crawled_at": crawled_at,
        "title_ko": "",
        "summary_ko": "",
    }


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^0-9a-z가-힣]+", "-", value.lower())
    return normalized.strip("-") or "trend"


def _looks_like_guide(title: str, description: str) -> bool:
    combined = f"{title} {description}".lower()
    guide_keywords = ("how to", "guide", "tips", "방법", "관리", "연출", "스타일")
    return any(keyword in combined for keyword in guide_keywords)


def _translation_cache_key(item: dict[str, Any]) -> str:
    return str(item.get("article_url") or item.get("display_title") or item.get("title") or "").strip()


def _load_translation_cache() -> dict[str, dict[str, str]]:
    if not TRANSLATION_CACHE_FILE.exists():
        return {}
    try:
        payload = json.loads(TRANSLATION_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}

    cache: dict[str, dict[str, str]] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        cache[key] = {
            "title_ko": str(value.get("title_ko") or "").strip(),
            "summary_ko": str(value.get("summary_ko") or "").strip(),
        }
    return cache


def _attach_korean_localizations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cache = _load_translation_cache()
    if not cache:
        return items

    localized_items: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        localized = cache.get(_translation_cache_key(row), {})
        row["title_ko"] = str(row.get("title_ko") or localized.get("title_ko") or "").strip()
        row["summary_ko"] = str(row.get("summary_ko") or localized.get("summary_ko") or "").strip()
        localized_items.append(row)
    return localized_items


def _metadata_key(value: Any) -> str:
    normalized = re.sub(r"[^0-9a-z가-힣]+", "-", str(value or "").strip().lower())
    return normalized.strip("-")


def _match_tokens(value: Any) -> set[str]:
    normalized = _metadata_key(value)
    if not normalized:
        return set()
    return {token for token in normalized.split("-") if len(token) > 1}


def _source_key(value: Any) -> str:
    return _metadata_key(value)


def _load_refined_payload() -> list[dict[str, Any]]:
    if not FALLBACK_INPUT_FILE.exists():
        return []
    try:
        payload = json.loads(FALLBACK_INPUT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


def _load_refined_metadata_lookup() -> dict[str, dict[str, Any]]:
    payload = _load_refined_payload()
    lookup: dict[str, dict[str, Any]] = {}
    for row in payload:
        candidate_keys = {
            _metadata_key(row.get("trend_name", "")),
            _metadata_key(row.get("article_title", "")),
            _metadata_key(row.get("article_url", "")),
        }
        for key in candidate_keys:
            if key and key not in lookup:
                lookup[key] = row
    return lookup


def _looks_like_article_candidate(*, article_title: str, summary: str, article_url: str) -> bool:
    try:
        from .latest_feed import _looks_like_hairstyle_only

        return _looks_like_hairstyle_only(
            title=article_title,
            summary=summary,
            article_url=article_url,
        )
    except Exception:
        return True


def _load_article_metadata_candidates() -> list[dict[str, Any]]:
    payload = _load_refined_payload()
    if not payload:
        return []

    grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload:
        article_url = str(row.get("article_url") or "").strip()
        if article_url:
            grouped_rows[article_url].append(row)

    candidates: list[dict[str, Any]] = []
    for article_url, rows in grouped_rows.items():
        first = rows[0]
        article_title = str(first.get("article_title") or "").strip()
        summary = " ".join(str(row.get("description") or "").strip()[:140] for row in rows[:3])
        if not _looks_like_article_candidate(
            article_title=article_title,
            summary=summary,
            article_url=article_url,
        ):
            continue

        row_token_sets = [
            _match_tokens(
                " ".join(
                    str(row.get(field) or "")
                    for field in ("trend_name", "article_title", "description", "hairstyle_text", "color_text")
                )
            )
            for row in rows
        ]
        article_tokens: set[str] = set()
        for token_set in row_token_sets:
            article_tokens.update(token_set)

        candidates.append(
            {
                "article_title": article_title,
                "article_url": article_url,
                "image_url": str(first.get("image_url") or "").strip(),
                "published_at": str(first.get("published_at") or "").strip(),
                "crawled_at": str(first.get("crawled_at") or "").strip(),
                "source": str(first.get("source") or "").strip(),
                "source_key": _source_key(first.get("source") or ""),
                "year": str(first.get("year") or "").strip(),
                "row_count": len(rows),
                "row_token_sets": row_token_sets,
                "article_tokens": article_tokens,
            }
        )

    return candidates


def _apply_metadata_fields(item: dict[str, Any], metadata: dict[str, Any] | None) -> dict[str, Any]:
    if metadata is None:
        return item

    row = dict(item)
    for field in ("article_title", "article_url", "image_url", "published_at", "crawled_at", "source", "year"):
        row[field] = str(row.get(field) or metadata.get(field) or "").strip()
    return row


def _article_candidate_score(item: dict[str, Any], candidate: dict[str, Any]) -> tuple[int, int]:
    item_tokens = _match_tokens(
        " ".join(
            str(item.get(field) or "")
            for field in ("display_title", "canonical_name", "summary", "search_text")
        )
    )
    if not item_tokens:
        return (-1, 0)

    tag_tokens = _match_tokens(" ".join(item.get("style_tags", []) or [])) | _match_tokens(
        " ".join(item.get("color_tags", []) or [])
    )
    candidate_article_tokens = set(candidate.get("article_tokens", set()))
    best_row_overlap = max((len(item_tokens & row_tokens) for row_tokens in candidate.get("row_token_sets", [])), default=0)
    article_overlap = len(item_tokens & candidate_article_tokens)
    union_size = len(item_tokens | candidate_article_tokens) or 1

    score = best_row_overlap * 12 + int((article_overlap / union_size) * 100)
    score += len(tag_tokens & candidate_article_tokens) * 15

    item_source_key = _source_key(item.get("source") or "")
    if item_source_key and item_source_key == candidate.get("source_key", ""):
        score += 18
    if str(item.get("year") or "").strip() and str(item.get("year") or "").strip() == str(candidate.get("year") or "").strip():
        score += 5

    score -= max(0, int(candidate.get("row_count", 0)) - 3)
    return score, best_row_overlap


def _select_article_metadata(item: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None

    item_source_key = _source_key(item.get("source") or "")
    same_source_candidates = [candidate for candidate in candidates if candidate.get("source_key") == item_source_key]
    scoped_candidates = same_source_candidates or candidates
    if item_source_key and not same_source_candidates:
        return None

    best_candidate = None
    best_score = -1
    best_overlap = 0
    for candidate in scoped_candidates:
        score, overlap = _article_candidate_score(item, candidate)
        if score > best_score:
            best_candidate = candidate
            best_score = score
            best_overlap = overlap

    if best_candidate is None:
        return None
    if best_score < ARTICLE_MATCH_SCORE_THRESHOLD or best_overlap < ARTICLE_MATCH_OVERLAP_THRESHOLD:
        return None
    return best_candidate


def _merge_refined_metadata(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = _load_refined_metadata_lookup()
    article_candidates = _load_article_metadata_candidates()
    if not lookup and not article_candidates:
        return items

    enriched_items: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        if row.get("article_url") and (row.get("published_at") or row.get("image_url")):
            enriched_items.append(row)
            continue

        matched_row = None
        for key in (
            _metadata_key(row.get("display_title", "")),
            _metadata_key(row.get("article_title", "")),
            _metadata_key(row.get("canonical_name", "")),
        ):
            if key and key in lookup:
                matched_row = lookup[key]
                break

        if matched_row is not None:
            row = _apply_metadata_fields(row, matched_row)
        else:
            row = _apply_metadata_fields(row, _select_article_metadata(row, article_candidates))

        enriched_items.append(row)

    return enriched_items


def _print_safety_report(report: dict[str, Any]) -> None:
    retitled_count = int(report.get("retitled_count", 0))
    dropped_count = int(report.get("dropped_count", 0))
    if retitled_count == 0 and dropped_count == 0:
        return

    print(
        "[rag_safety] sanitized"
        f" retitled={retitled_count}"
        f" dropped={dropped_count}"
        f" input={report.get('input_count', 0)}"
        f" output={report.get('output_count', 0)}"
    )
    for example in report.get("retitled_examples", []) or []:
        print(f"  retitled: {example.get('from', '')} -> {example.get('to', '')}")
    for example in report.get("dropped_examples", []) or []:
        print(f"  dropped: {example.get('title', '')} ({example.get('reason', '')})")


def build_collection() -> chromadb.api.models.Collection.Collection:
    ensure_directories()
    data = load_data()
    print(f"Loaded {len(data)} trend records.")

    client = create_persistent_client(CHROMA_TRENDS_DIR)

    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"Deleted existing collection '{COLLECTION_NAME}'.")
    except (ValueError, NotFoundError):
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "Hair trend RAG data maintained inside final_web backend"},
    )

    batch_size = 500
    for start in range(0, len(data), batch_size):
        batch = data[start : start + batch_size]
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for offset, item in enumerate(batch):
            idx = start + offset
            ids.append(f"trend_{idx:04d}")
            documents.append(item.get("search_text", ""))
            metadatas.append(
                {
                    "canonical_name": item.get("canonical_name", ""),
                    "display_title": item.get("display_title", ""),
                    "category": item.get("category", ""),
                    "style_tags": ", ".join(item.get("style_tags", [])),
                    "color_tags": ", ".join(item.get("color_tags", [])),
                    "summary": item.get("summary", ""),
                    "source": item.get("source", ""),
                    "year": item.get("year", ""),
                    "article_title": item.get("article_title", ""),
                    "article_url": item.get("article_url", ""),
                    "image_url": item.get("image_url", ""),
                    "published_at": item.get("published_at", ""),
                    "crawled_at": item.get("crawled_at", ""),
                    "title_ko": item.get("title_ko", ""),
                    "summary_ko": item.get("summary_ko", ""),
                }
            )

        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        print(f"  inserted [{start + len(batch)}/{len(data)}]")

    print("\n====== vectorization complete ======")
    print(f"collection: {COLLECTION_NAME} ({collection.count()} docs)")
    print(f"store path: {CHROMA_TRENDS_DIR}")
    return collection


def query_test(collection: chromadb.api.models.Collection.Collection, query_text: str, n_results: int = 5) -> None:
    del collection
    from .rag_query import retrieve

    results = retrieve(query_text, n_results=n_results)
    print(_console_safe(f'\nquery: "{query_text}"'))
    print(_console_safe("-" * 60))
    for index, metadata in enumerate(results, start=1):
        print(_console_safe(f"  [{index}] {metadata['title']}"))
        print(_console_safe(f"      category: {metadata['category']} | source: {metadata['source']}"))
        print()


def main() -> None:
    collection = build_collection()
    client = create_persistent_client(CHROMA_TRENDS_DIR)
    collection = client.get_collection(COLLECTION_NAME)
    query_test(collection, "2026 spring blonde hair trend")
    query_test(collection, "요즘 유행하는 단발 헤어스타일")
    query_test(collection, "celebrity bob haircut")


def _console_safe(value: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return value.encode(encoding, errors="replace").decode(encoding, errors="replace")


if __name__ == "__main__":
    main()
