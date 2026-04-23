from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import shutil
import threading
from pathlib import Path
from typing import Any

import chromadb
from chromadb.errors import NotFoundError
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from .prompt_builder import DESIGNER_INSTRUCTOR_PERSONA_PATH
from app.trend_pipeline.chroma_client import create_persistent_client
from app.trend_pipeline.paths import RAG_STORE_DIR


logger = logging.getLogger(__name__)

CHATBOT_RAG_DATASET_PATH = (
    DESIGNER_INSTRUCTOR_PERSONA_PATH.parent
    / "designer_support_dataset_v5_final_revised_optimized.json"
)
CHATBOT_RAG_CHROMA_DIR = RAG_STORE_DIR / "chromadb_chatbot"
CHATBOT_RAG_MANIFEST_PATH = CHATBOT_RAG_CHROMA_DIR / "manifest.json"
CHATBOT_RAG_COLLECTION_NAME = "designer_support_docs"

DEFAULT_TOP_K = 4
DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 180
DEFAULT_EMBEDDING_DIM = 192
EMBEDDING_VERSION = "hashed-token-v2"
TEXT_CLEANUP_VERSION = "chatbot-rag-cleanup-v2"

FOLLOWUP_QUERY_KEYWORDS = (
    "그 다음",
    "다음 순서",
    "계속",
    "이어서",
    "나머지",
    "전체 순서",
)
DOMAIN_SIGNAL_KEYWORDS = (
    "컷",
    "펌",
    "레이어드",
    "보브",
    "가발",
    "염색",
    "컬러",
    "와인딩",
    "롯드",
    "업스타일",
    "블로우",
    "드라이",
    "c컬",
    "s컬",
)
STOPWORD_TOKENS = {
    "알려줘",
    "알려주세요",
    "뭐야",
    "무엇",
    "설명",
    "가이드",
    "방법",
    "정리",
}
JOSA_SUFFIXES = (
    "으로는",
    "에서는",
    "에게는",
    "으로",
    "에서",
    "에게",
    "까지",
    "부터",
    "처럼",
    "만",
    "을",
    "를",
    "이",
    "가",
    "은",
    "는",
    "와",
    "과",
    "도",
)

_BUILD_LOCK = threading.Lock()
REFERENCE_INJECTION_PATTERNS = (
    re.compile(
        r"\b(ignore|disregard|forget|override)\b.{0,48}\b(previous|prior|system|developer|instruction|instructions|rule|rules)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(show|reveal|print|dump|expose)\b.{0,48}\b(system|developer|hidden|internal)\b.{0,24}\b(prompt|message|instruction|instructions|rule|rules)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(system prompt|developer message|hidden instruction|act as)\b", re.IGNORECASE),
    re.compile(r"(시스템 프롬프트|개발자 메시지|숨겨진 지침|이전 지침 무시)", re.IGNORECASE),
)


def _normalize_text(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    cleaned = re.sub(r"\s+([,.!?])", r"\1", cleaned)
    return cleaned


def _excerpt(value: str, *, limit: int = 180) -> str:
    normalized = _normalize_text(value)
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _looks_like_instruction_text(value: str) -> bool:
    normalized = _normalize_text(value)
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in REFERENCE_INJECTION_PATTERNS)


def _rag_top_k() -> int:
    raw = (
        os.environ.get("MIRRAI_MODEL_CHATBOT_RAG_TOP_K")
        or os.environ.get("MIRRAI_MODEL_CHATBOT_LOCAL_TOP_K")
        or str(DEFAULT_TOP_K)
    ).strip()
    try:
        return max(1, min(int(raw), 6))
    except ValueError:
        return DEFAULT_TOP_K


def _chunk_size() -> int:
    raw = (
        os.environ.get("MIRRAI_MODEL_CHATBOT_RAG_CHUNK_SIZE")
        or os.environ.get("MIRRAI_MODEL_CHATBOT_LOCAL_CHUNK_SIZE")
        or str(DEFAULT_CHUNK_SIZE)
    ).strip()
    try:
        return max(300, int(raw))
    except ValueError:
        return DEFAULT_CHUNK_SIZE


def _chunk_overlap() -> int:
    raw = (
        os.environ.get("MIRRAI_MODEL_CHATBOT_RAG_CHUNK_OVERLAP")
        or os.environ.get("MIRRAI_MODEL_CHATBOT_LOCAL_CHUNK_OVERLAP")
        or str(DEFAULT_CHUNK_OVERLAP)
    ).strip()
    try:
        return max(40, min(int(raw), _chunk_size() // 2))
    except ValueError:
        return DEFAULT_CHUNK_OVERLAP


def _embedding_dim() -> int:
    raw = (
        os.environ.get("MIRRAI_MODEL_CHATBOT_RAG_EMBED_DIM")
        or os.environ.get("MIRRAI_MODEL_CHATBOT_LOCAL_EMBED_DIM")
        or str(DEFAULT_EMBEDDING_DIM)
    ).strip()
    try:
        return max(64, min(int(raw), 512))
    except ValueError:
        return DEFAULT_EMBEDDING_DIM


def _stem_token(token: str) -> str:
    normalized = token.strip().lower()
    for suffix in sorted(JOSA_SUFFIXES, key=len, reverse=True):
        if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 2:
            return normalized[: -len(suffix)]
    return normalized


def _normalize_tokens(value: str) -> set[str]:
    normalized = re.sub(r"[^0-9a-zA-Z가-힣]+", " ", _normalize_text(value).lower())
    tokens: set[str] = set()
    for token in normalized.split():
        stemmed = _stem_token(token)
        if len(stemmed) <= 1 or stemmed in STOPWORD_TOKENS:
            continue
        tokens.add(stemmed)
    return tokens


def _token_overlap_score(left_value: str, right_value: str) -> int:
    left_tokens = _normalize_tokens(left_value)
    right_tokens = _normalize_tokens(right_value)
    matched_tokens = 0

    for left_token in left_tokens:
        if any(
            left_token == right_token
            or left_token in right_token
            or right_token in left_token
            for right_token in right_tokens
        ):
            matched_tokens += 1

    return matched_tokens


def _embed_text(value: str) -> list[float]:
    dim = _embedding_dim()
    vector = [0.0] * dim
    features = sorted(_normalize_tokens(value))
    if not features:
        return vector

    for feature in features:
        digest = hashlib.sha256(feature.encode("utf-8")).digest()
        for slot in range(0, 8, 2):
            index = int.from_bytes(digest[slot : slot + 2], "big") % dim
            sign = 1.0 if digest[slot + 8] % 2 == 0 else -1.0
            weight = 1.0 + (digest[slot + 16] / 255.0) * 0.25
            vector[index] += sign * weight

    norm = math.sqrt(sum(item * item for item in vector))
    if norm <= 1e-12:
        return vector
    return [item / norm for item in vector]


class _HashedTokenEmbeddings(Embeddings):
    """Wrap the existing local embedding logic in the LangChain interface."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_embed_text(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return _embed_text(text)


def _manifest_payload() -> dict[str, Any]:
    if not CHATBOT_RAG_DATASET_PATH.exists():
        return {}
    stat = CHATBOT_RAG_DATASET_PATH.stat()
    return {
        "dataset_path": str(CHATBOT_RAG_DATASET_PATH),
        "dataset_mtime_ns": stat.st_mtime_ns,
        "dataset_size": stat.st_size,
        "collection_name": CHATBOT_RAG_COLLECTION_NAME,
        "chunk_size": _chunk_size(),
        "chunk_overlap": _chunk_overlap(),
        "embedding_dim": _embedding_dim(),
        "embedding_version": EMBEDDING_VERSION,
        "text_cleanup_version": TEXT_CLEANUP_VERSION,
    }


def _manifest_is_current() -> bool:
    if not CHATBOT_RAG_MANIFEST_PATH.exists():
        return False
    try:
        stored = json.loads(CHATBOT_RAG_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return stored == _manifest_payload()


def _write_manifest() -> None:
    CHATBOT_RAG_CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    CHATBOT_RAG_MANIFEST_PATH.write_text(
        json.dumps(_manifest_payload(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_dataset_rows() -> list[dict[str, Any]]:
    if not CHATBOT_RAG_DATASET_PATH.exists():
        return []
    try:
        payload = json.loads(CHATBOT_RAG_DATASET_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("[chatbot_rag_dataset_invalid] path=%s", CHATBOT_RAG_DATASET_PATH)
        return []
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


def _flatten_table(table: Any) -> str:
    if not isinstance(table, list):
        return ""
    cells: list[str] = []
    for row in table:
        if not isinstance(row, list):
            continue
        for cell in row:
            cleaned = _normalize_text("" if cell is None else str(cell))
            if cleaned:
                cells.append(cleaned)
    return " | ".join(cells)


def _flatten_page_text(page: dict[str, Any]) -> str:
    page_text = _normalize_text(str(page.get("text") or ""))
    table_text = " ".join(
        flattened for flattened in (_flatten_table(table) for table in page.get("tables") or []) if flattened
    )
    return _normalize_text(" ".join(part for part in [page_text, table_text] if part))


def _chunk_document(text: str) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    size = _chunk_size()
    overlap = _chunk_overlap()
    if len(normalized) <= size:
        return [normalized]

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + size)
        chunks.append(normalized[start:end].strip())
        if end >= len(normalized):
            break
        start = max(0, end - overlap)
    return [chunk for chunk in chunks if chunk]


def _build_rag_documents() -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for row in _load_dataset_rows():
        source = _normalize_text(str(row.get("source") or "reference.pdf"))
        for page in row.get("content") or []:
            if not isinstance(page, dict):
                continue
            page_number = int(page.get("page_number") or 1)
            page_text = _flatten_page_text(page)
            if not page_text:
                continue
            for chunk_index, chunk in enumerate(_chunk_document(page_text), start=1):
                documents.append(
                    {
                        "id": f"{source}:{page_number}:{chunk_index}",
                        "document": chunk,
                        "metadata": {
                            "source": source,
                            "page_number": page_number,
                            "chunk_index": chunk_index,
                        },
                    }
                )
    return documents


def _create_client() -> chromadb.PersistentClient:
    CHATBOT_RAG_CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return create_persistent_client(CHATBOT_RAG_CHROMA_DIR)


def _create_vector_store() -> Chroma:
    return Chroma(
        client=_create_client(),
        collection_name=CHATBOT_RAG_COLLECTION_NAME,
        embedding_function=_HashedTokenEmbeddings(),
        create_collection_if_not_exists=True,
    )


def _reset_collection() -> None:
    if CHATBOT_RAG_CHROMA_DIR.exists():
        shutil.rmtree(CHATBOT_RAG_CHROMA_DIR, ignore_errors=True)


def ensure_chatbot_rag_index() -> int:
    with _BUILD_LOCK:
        if _manifest_is_current():
            try:
                client = _create_client()
                collection = client.get_collection(CHATBOT_RAG_COLLECTION_NAME)
                return collection.count()
            except Exception:
                pass

        _reset_collection()
        vector_store = _create_vector_store()
        documents = _build_rag_documents()
        if documents:
            vector_store.add_documents(
                documents=[
                    Document(
                        page_content=str(item["document"] or ""),
                        metadata=dict(item["metadata"] or {}),
                    )
                    for item in documents
                ],
                ids=[str(item["id"]) for item in documents],
            )
        _write_manifest()
        return len(documents)


def _query_collection(question: str, *, limit: int) -> list[dict[str, Any]]:
    try:
        ensure_chatbot_rag_index()
        results = _create_vector_store().similarity_search_with_score(question, k=limit)
    except Exception as exc:
        logger.warning("[chatbot_rag_chroma_retry] reason=%s", exc)
        ensure_chatbot_rag_index()
        results = _create_vector_store().similarity_search_with_score(question, k=limit)

    matches: list[dict[str, Any]] = []
    for document, distance in results:
        if not document.page_content or not isinstance(document.metadata, dict):
            continue
        score = max(0.0, 1.0 - float(distance or 0.0))
        matches.append(
            {
                "document": str(document.page_content),
                "metadata": document.metadata,
                "score": score,
            }
        )
    return matches


def _lexical_matches(question: str, *, limit: int) -> list[dict[str, Any]]:
    scored_matches: list[dict[str, Any]] = []
    for item in _build_rag_documents():
        document = str(item["document"] or "")
        metadata = item["metadata"]
        lexical_overlap = _token_overlap_score(question, document)
        if lexical_overlap <= 0:
            continue
        bonus = 2 if any(keyword in question.lower() for keyword in DOMAIN_SIGNAL_KEYWORDS if keyword) else 0
        scored_matches.append(
            {
                "document": document,
                "metadata": metadata,
                "score": float(lexical_overlap + bonus),
            }
        )

    scored_matches.sort(
        key=lambda item: (
            -float(item.get("score") or 0.0),
            int((item.get("metadata") or {}).get("page_number") or 0),
            int((item.get("metadata") or {}).get("chunk_index") or 0),
        )
    )
    return scored_matches[:limit]


def retrieve_chatbot_rag_matches(question: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    normalized_question = _normalize_text(question)
    if not normalized_question:
        return []

    resolved_limit = max(1, limit or _rag_top_k())
    vector_matches = _query_collection(normalized_question, limit=resolved_limit)
    lexical_matches = _lexical_matches(normalized_question, limit=resolved_limit)

    merged: dict[tuple[str, int, int], dict[str, Any]] = {}
    for match in [*vector_matches, *lexical_matches]:
        if _looks_like_instruction_text(str(match.get("document") or "")):
            continue
        metadata = match.get("metadata") or {}
        key = (
            str(metadata.get("source") or ""),
            int(metadata.get("page_number") or 0),
            int(metadata.get("chunk_index") or 0),
        )
        existing = merged.get(key)
        if existing is None or float(match.get("score") or 0.0) > float(existing.get("score") or 0.0):
            merged[key] = match

    ranked = sorted(
        merged.values(),
        key=lambda item: (
            -float(item.get("score") or 0.0),
            int((item.get("metadata") or {}).get("page_number") or 0),
            int((item.get("metadata") or {}).get("chunk_index") or 0),
        ),
    )
    return ranked[:resolved_limit]


def _normalize_conversation_history(
    conversation_history: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    normalized_history: list[dict[str, str]] = []
    for item in conversation_history or []:
        if not isinstance(item, dict):
            continue
        role = _normalize_text(str(item.get("role") or "user")).lower()
        content = _normalize_text(str(item.get("content") or ""))
        if not content or role in {"bot", "assistant", "chatbot", "model"}:
            continue
        if _looks_like_instruction_text(content):
            continue
        normalized_history.append(
            {
                "role": "user",
                "content": content,
            }
        )
    return normalized_history[-8:]


def _extract_recent_bot_step_context(normalized_history: list[dict[str, str]]) -> str:
    for item in reversed(normalized_history):
        if item.get("role") != "bot":
            continue
        content = item.get("content") or ""
        if any(marker in content for marker in ("1.", "2.", "첫", "다음", "마지막")):
            return content
    return ""


def _has_domain_signal(question: str) -> bool:
    normalized_question = _normalize_text(question).lower()
    return any(keyword in normalized_question for keyword in DOMAIN_SIGNAL_KEYWORDS)


def _is_followup_request(question: str) -> bool:
    normalized_question = _normalize_text(question)
    return any(keyword in normalized_question for keyword in FOLLOWUP_QUERY_KEYWORDS)


def _is_context_light_question(question: str) -> bool:
    if _has_domain_signal(question):
        return False
    tokens = _normalize_tokens(question)
    return len(tokens) <= 1


def _resolve_contextual_question(
    question: str,
    *,
    conversation_history: list[dict[str, Any]] | None = None,
) -> str:
    normalized_question = _normalize_text(question)
    if not normalized_question:
        return normalized_question

    normalized_history = _normalize_conversation_history(conversation_history)
    if not normalized_history:
        return normalized_question

    should_use_context = (
        _is_followup_request(normalized_question)
        or _is_context_light_question(normalized_question)
    )
    if not should_use_context:
        return normalized_question

    previous_user_messages = [
        item["content"]
        for item in normalized_history
        if item.get("role") == "user" and item.get("content") != normalized_question
    ]
    if not previous_user_messages:
        return normalized_question

    context_parts = [previous_user_messages[-1], normalized_question]
    return _normalize_text(" ".join(part for part in context_parts if part))


def _format_matches_for_prompt(matches: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for match in matches[:5]:
        metadata = match.get("metadata") or {}
        source_name = _normalize_text(str(metadata.get("source") or "reference"))
        page_number = metadata.get("page_number")
        page_label = f" p.{page_number}" if page_number not in (None, "") else ""
        lines.append(
            f"- {source_name}{page_label}: {_excerpt(str(match.get('document') or ''), limit=180)}"
        )
    return "\n".join(lines)


def build_chatbot_rag_context(
    *,
    message: str,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    question = _normalize_text(message)
    if not question:
        return {
            "search_query": "",
            "matched_sources": [],
            "source_context": "",
            "dataset_source": "chatbot_rag_chromadb",
            "provider": "chatbot_rag",
        }

    search_query = _resolve_contextual_question(
        question,
        conversation_history=conversation_history,
    )
    matches = retrieve_chatbot_rag_matches(search_query, limit=_rag_top_k())
    matched_sources = [
        {
            "source": (match.get("metadata") or {}).get("source"),
            "page_number": (match.get("metadata") or {}).get("page_number"),
            "chunk_index": (match.get("metadata") or {}).get("chunk_index"),
            "score": round(float(match.get("score") or 0.0), 4),
            "excerpt": _excerpt(str(match.get("document") or "")),
        }
        for match in matches
    ]

    return {
        "search_query": search_query,
        "matched_sources": matched_sources,
        "source_context": _format_matches_for_prompt(matches),
        "dataset_source": "chatbot_rag_chromadb",
        "provider": "chatbot_rag",
    }


def get_chatbot_rag_status() -> dict[str, Any]:
    dataset_exists = CHATBOT_RAG_DATASET_PATH.exists()
    collection_exists = CHATBOT_RAG_CHROMA_DIR.exists()
    document_count = None

    try:
        if collection_exists:
            client = _create_client()
            collection = client.get_collection(CHATBOT_RAG_COLLECTION_NAME)
            document_count = collection.count()
    except (NotFoundError, Exception):
        document_count = None

    return {
        "provider": "chatbot_rag",
        "dataset_path": str(CHATBOT_RAG_DATASET_PATH),
        "dataset_exists": dataset_exists,
        "store_path": str(CHATBOT_RAG_CHROMA_DIR),
        "collection_name": CHATBOT_RAG_COLLECTION_NAME,
        "collection_ready": bool(document_count),
        "document_count": document_count,
        "manifest_current": _manifest_is_current(),
        "embedding_version": EMBEDDING_VERSION,
        "embedding_dim": _embedding_dim(),
    }
