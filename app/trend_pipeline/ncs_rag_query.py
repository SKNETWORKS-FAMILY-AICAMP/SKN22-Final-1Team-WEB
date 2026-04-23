from __future__ import annotations

from functools import lru_cache
import re
import unicodedata
from typing import Any

import chromadb

from .chroma_client import create_persistent_client
from .paths import CHROMA_NCS_DIR, ensure_directories


COLLECTION_NAME = "hair_ncs_manuals"
TOP_K = 5


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).lower()
    normalized = re.sub(r"[^0-9a-z가-힣]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _tokenize(value: str) -> set[str]:
    return {token for token in _normalize_text(value).split(" ") if len(token) > 1}


@lru_cache(maxsize=1)
def _get_collection():
    ensure_directories()
    client = create_persistent_client(CHROMA_NCS_DIR)
    return client.get_collection(COLLECTION_NAME)


def retrieve(query: str, n_results: int = TOP_K, expand: bool = True) -> list[dict[str, Any]]:
    del expand

    collection = _get_collection()
    raw = collection.get(include=["documents", "metadatas"])
    query_tokens = _tokenize(query)

    docs: list[dict[str, Any]] = []
    for document, metadata in zip(raw.get("documents", []), raw.get("metadatas", [])):
        meta = metadata or {}
        title = str(meta.get("display_title", "")).strip()
        category = str(meta.get("category", "")).strip()
        service_type = str(meta.get("service_type", "")).strip()
        target_conditions = str(meta.get("target_conditions", "")).strip()
        tools = str(meta.get("tools", "")).strip()
        steps = str(meta.get("steps", "")).strip()
        cautions = str(meta.get("cautions", "")).strip()
        summary = str(meta.get("summary", "")).strip()
        source_document_name = str(meta.get("source_document_name", "")).strip()
        source_page = str(meta.get("source_page", "")).strip()
        lexical_text = " ".join(
            chunk
            for chunk in (
                title,
                category,
                service_type,
                target_conditions,
                tools,
                steps,
                cautions,
                summary,
                source_document_name,
                str(document or ""),
            )
            if chunk
        )
        overlap = len(query_tokens & _tokenize(lexical_text))
        docs.append(
            {
                "title": title,
                "category": category,
                "service_type": service_type,
                "target_conditions": target_conditions,
                "tools": tools,
                "steps": steps,
                "cautions": cautions,
                "summary": summary,
                "source_document_name": source_document_name,
                "source_page": source_page,
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
                    f"서비스 유형: {doc.get('service_type', '')}",
                    f"대상 조건: {doc.get('target_conditions', '')}",
                    f"도구: {doc.get('tools', '')}",
                    f"시술 순서: {doc.get('steps', '')}",
                    f"주의사항: {doc.get('cautions', '')}",
                    f"요약: {doc.get('summary', '')}",
                    f"출처: {doc.get('source_document_name', '')} p.{doc.get('source_page', '')}",
                ]
            )
        )
    return "\n\n".join(context_parts)
