from __future__ import annotations

from functools import lru_cache
import re
import unicodedata
from typing import Any

import chromadb

from .chroma_client import create_persistent_client
from .paths import CHROMA_TRENDS_DIR, ensure_directories


COLLECTION_NAME = "hair_trends"
TOP_K = 5


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).lower()
    normalized = re.sub(r"[^0-9a-z가-힣 ]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _tokenize(value: str) -> set[str]:
    return {token for token in _normalize_text(value).split(" ") if len(token) > 1}


@lru_cache(maxsize=1)
def _get_collection():
    ensure_directories()
    client = create_persistent_client(CHROMA_TRENDS_DIR)
    return client.get_collection(COLLECTION_NAME)


def retrieve(query: str, n_results: int = TOP_K, expand: bool = True) -> list[dict[str, Any]]:
    del expand

    collection = _get_collection()
    raw = collection.get(include=["documents", "metadatas"])

    query_tokens = _tokenize(query)
    docs: list[dict[str, Any]] = []
    for document, metadata in zip(
        raw.get("documents", []),
        raw.get("metadatas", []),
    ):
        meta = metadata or {}
        title = str(meta.get("title_ko") or meta.get("display_title") or "").strip()
        category = str(meta.get("category", "")).strip()
        summary = str(meta.get("summary_ko") or meta.get("summary") or "").strip()
        style_tags = str(meta.get("style_tags", "")).strip()
        color_tags = str(meta.get("color_tags", "")).strip()
        source = str(meta.get("source", "")).strip()
        year = str(meta.get("year", "")).strip()
        lexical_text = " ".join(
            chunk
            for chunk in (
                title,
                category,
                summary,
                style_tags,
                color_tags,
                source,
                str(document or ""),
            )
            if chunk
        )
        overlap = len(query_tokens & _tokenize(lexical_text))
        docs.append(
            {
                "title": title,
                "category": category,
                "summary": summary,
                "style_tags": style_tags,
                "color_tags": color_tags,
                "source": source,
                "year": year,
                "overlap_score": overlap,
            }
        )

    docs.sort(
        key=lambda item: (
            -int(item.get("overlap_score", 0) or 0),
            str(item.get("title") or ""),
        )
    )
    return docs[:n_results]


def build_context(docs: list[dict[str, Any]]) -> str:
    context_parts: list[str] = []
    for index, doc in enumerate(docs, start=1):
        context_parts.append(
            "\n".join(
                [
                    f"[자료 {index}]",
                    f"제목: {doc.get('title', '')}",
                    f"카테고리: {doc.get('category', '')}",
                    f"요약: {doc.get('summary', '')}",
                    f"스타일 태그: {doc.get('style_tags', '')}",
                    f"컬러 태그: {doc.get('color_tags', '')}",
                    f"출처: {doc.get('source', '')} ({doc.get('year', '')})",
                ]
            )
        )
    return "\n\n".join(context_parts)
