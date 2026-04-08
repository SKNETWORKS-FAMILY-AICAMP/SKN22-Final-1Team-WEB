from __future__ import annotations

import ast
import hashlib
import json
import logging
import math
import os
import re
import threading
from pathlib import Path
from typing import Any

import chromadb
from chromadb.errors import NotFoundError
from django.utils import timezone

from app.services.chatbot_prompt_builder import DESIGNER_INSTRUCTOR_PERSONA_PATH
from app.trend_pipeline.paths import RAG_STORE_DIR


logger = logging.getLogger(__name__)

CHATBOT_DATASET_PATH = DESIGNER_INSTRUCTOR_PERSONA_PATH.parent / "designer_support_dataset_v5_final_revised_optimized.json"
CHATBOT_CHROMA_DIR = RAG_STORE_DIR / "chromadb_chatbot"
CHATBOT_CHROMA_MANIFEST = CHATBOT_CHROMA_DIR / "manifest.json"
CHATBOT_COLLECTION_NAME = "designer_support_docs"
DEFAULT_TOP_K = 3
DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 180
DEFAULT_EMBEDDING_DIM = 192
EMBEDDING_VERSION = "hashed-token-v1"
TEXT_CLEANUP_VERSION = "chatbot-cleanup-v3"

_BUILD_LOCK = threading.Lock()
GREETING_KEYWORDS = ("안녕", "안녕하세요", "반가워", "반갑습니다", "hello", "hi", "헬로", "ㅎㅇ")
THANKS_KEYWORDS = ("고마워", "고맙", "감사")
NOISY_CLAUSE_KEYWORDS = ("교수", "학습자", "평가", "도구 분류", "이미지 기능")
LOW_VALUE_DOCUMENT_KEYWORDS = (
    "재료·자료",
    "기기(장비",
    "기기(장비·공구)",
    "거울과 의자",
    "거울, 의자",
    "염색저울",
    "염색볼",
    "타이머",
)
NOISY_DOCUMENT_KEYWORDS = (
    "성취수준",
    "평가 항목",
    "자료의 작성 능력",
    "설명 가능 여부",
    "고객 관리 차트",
    "고 객 명",
    "방문경로",
    "평가자 질문",
)
STOPWORD_TOKENS = {"알려줘", "알려주세요", "말해줘", "뭐야", "뭐예요", "방법", "설명", "정리", "해주세요"}
JOSA_SUFFIXES = (
    "에게서", "으로는", "으로도", "으로의", "에게는", "에게도", "에게", "에서", "으로", "와의", "과의",
    "은", "는", "이", "가", "을", "를", "와", "과", "의", "에", "도", "만", "로", "나", "요",
)
QUESTION_SOURCE_HINTS = (
    (("염색", "컬러", "탈색"), ("헤어컬러", "컬러", "염색")),
    (("커트", "컷", "레이어"), ("헤어커트", "커트")),
    (("펌", "웨이브"), ("헤어펌", "펌")),
    (("샴푸", "클리닉", "트리트먼트"), ("샴푸", "클리닉")),
    (("가발",), ("가발",)),
)
CAUTION_QUERY_KEYWORDS = ("주의", "주의사항", "유의", "알레르기", "패치", "부작용", "민감")
CAUTION_DOC_KEYWORDS = (
    "주의",
    "유의",
    "알레르기",
    "패치",
    "부작용",
    "민감",
    "두피",
    "손상",
    "테스트",
    "보호",
)

REFERENCE_TOKEN_PATTERN = re.compile(
    r"(?:[\[<(]?\s*(?:그림|도표|표)\s*\d+(?:-\d+)?\s*[\])>]?\s*(?:과 같이|와 같이)?)"
)
LEADING_STEP_PATTERN = re.compile(r"^(?:\(?\d+\)?\s*)+")
NOISY_PREFIX_PATTERN = re.compile(
    r"^(?:수행\s*tip|교수·학습 방법\s*교수 방법|교수 방법|학습자 활동|평가 방법)\s*[-:]?\s*"
)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _cleanup_source_text(value: str) -> str:
    text = str(value or "")
    text = REFERENCE_TOKEN_PATTERN.sub(" ", text)
    text = re.sub(r"출처:\s*.*?p\.\s*\d+\.", " ", text)
    text = re.sub(r"수행\s*tip", " ", text)
    text = re.sub(r"도해도\w*", " ", text)
    text = re.sub(r"\b(?:사진 자료|이미지 자료|동영상 자료)\b", " ", text)
    return _normalize_text(text)


def _canonicalize_search_terms(value: str) -> str:
    normalized = _normalize_text(value).lower()
    replacements = {
        "레이어드": "레이어",
        "컷트": "커트",
        "컷": "커트",
        "유의 사항": "주의사항",
        "유의사항": "주의사항",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return normalized


def _stem_token(token: str) -> str:
    normalized = token.strip()
    for suffix in sorted(JOSA_SUFFIXES, key=len, reverse=True):
        if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 2:
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def _normalize_tokens(value: str) -> set[str]:
    normalized = re.sub(r"[^0-9a-zA-Z가-힣]+", " ", _canonicalize_search_terms(value))
    tokens: set[str] = set()
    for token in normalized.split():
        stemmed = _stem_token(token)
        if len(stemmed) <= 1:
            continue
        if stemmed in STOPWORD_TOKENS:
            continue
        tokens.add(stemmed)
    return tokens


def _source_bonus_for_question(question: str, source_name: str) -> int:
    normalized_question = _canonicalize_search_terms(question)
    normalized_source = _canonicalize_search_terms(source_name)

    best_bonus = 0
    for question_keywords, source_keywords in QUESTION_SOURCE_HINTS:
        if any(keyword in normalized_question for keyword in question_keywords):
            if any(keyword in normalized_source for keyword in source_keywords):
                best_bonus = max(best_bonus, 2)
            else:
                best_bonus = max(best_bonus, 0)
    return best_bonus


def _source_penalty_for_question(question: str, source_name: str) -> int:
    normalized_question = _canonicalize_search_terms(question)
    normalized_source = _canonicalize_search_terms(source_name)
    if "가발" in normalized_source and "가발" not in normalized_question:
        return -4
    return 0


def _content_bonus_for_question(question: str, document: str) -> int:
    normalized_question = _canonicalize_search_terms(question)
    normalized_document = _canonicalize_search_terms(document)
    bonus = 0
    if any(keyword in normalized_question for keyword in CAUTION_QUERY_KEYWORDS):
        caution_hits = sum(1 for keyword in CAUTION_DOC_KEYWORDS if keyword in normalized_document)
        bonus += min(caution_hits, 4)
        if any(keyword in normalized_document for keyword in ("패치 테스트", "패치테스트", "알레르기", "민감도")):
            bonus += 3
        if any(keyword in normalized_document for keyword in ("전처리", "보호제", "두피 보호", "피부 보호")):
            bonus += 2
    if any(keyword in normalized_question for keyword in ("염색", "컬러", "탈색")):
        if any(keyword in normalized_document for keyword in ("염색", "염모제", "헤어컬러", "컬러", "산화제")):
            bonus += 2
        if any(keyword in normalized_document for keyword in ("패치", "알레르기", "전처리", "보호제")):
            bonus += 1
    return bonus


def _is_noisy_document(value: str) -> bool:
    cleaned = _normalize_text(value)
    return any(keyword in cleaned for keyword in NOISY_DOCUMENT_KEYWORDS)


def _document_penalty(document: str) -> int:
    normalized_document = _normalize_text(document)
    penalty = 0
    if any(keyword in normalized_document for keyword in LOW_VALUE_DOCUMENT_KEYWORDS):
        penalty -= 4
    if normalized_document.count(" - ") >= 4:
        penalty -= 2
    if normalized_document.count(",") >= 8:
        penalty -= 1
    return penalty


def _chatbot_top_k() -> int:
    raw = os.environ.get("MIRRAI_MODEL_CHATBOT_LOCAL_TOP_K", str(DEFAULT_TOP_K)).strip()
    try:
        return max(1, min(int(raw), 5))
    except ValueError:
        return DEFAULT_TOP_K


def _chunk_size() -> int:
    raw = os.environ.get("MIRRAI_MODEL_CHATBOT_LOCAL_CHUNK_SIZE", str(DEFAULT_CHUNK_SIZE)).strip()
    try:
        return max(300, int(raw))
    except ValueError:
        return DEFAULT_CHUNK_SIZE


def _chunk_overlap() -> int:
    raw = os.environ.get("MIRRAI_MODEL_CHATBOT_LOCAL_CHUNK_OVERLAP", str(DEFAULT_CHUNK_OVERLAP)).strip()
    try:
        return max(40, min(int(raw), _chunk_size() // 2))
    except ValueError:
        return DEFAULT_CHUNK_OVERLAP


def _embedding_dim() -> int:
    raw = os.environ.get("MIRRAI_MODEL_CHATBOT_LOCAL_EMBED_DIM", str(DEFAULT_EMBEDDING_DIM)).strip()
    try:
        return max(64, min(int(raw), 512))
    except ValueError:
        return DEFAULT_EMBEDDING_DIM


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

    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 1e-12:
        return vector
    return [value / norm for value in vector]


def _manifest_payload() -> dict[str, Any]:
    if not CHATBOT_DATASET_PATH.exists():
        return {}
    stat = CHATBOT_DATASET_PATH.stat()
    return {
        "dataset_path": str(CHATBOT_DATASET_PATH),
        "dataset_mtime_ns": stat.st_mtime_ns,
        "dataset_size": stat.st_size,
        "collection_name": CHATBOT_COLLECTION_NAME,
        "chunk_size": _chunk_size(),
        "chunk_overlap": _chunk_overlap(),
        "embedding_dim": _embedding_dim(),
        "embedding_version": EMBEDDING_VERSION,
        "text_cleanup_version": TEXT_CLEANUP_VERSION,
    }


def _manifest_is_current() -> bool:
    if not CHATBOT_CHROMA_MANIFEST.exists():
        return False
    try:
        stored = json.loads(CHATBOT_CHROMA_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return stored == _manifest_payload()


def _write_manifest() -> None:
    CHATBOT_CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    CHATBOT_CHROMA_MANIFEST.write_text(
        json.dumps(_manifest_payload(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_dataset_rows() -> list[dict[str, Any]]:
    if not CHATBOT_DATASET_PATH.exists():
        return []
    try:
        payload = json.loads(CHATBOT_DATASET_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("[local_chatbot_dataset_invalid] path=%s", CHATBOT_DATASET_PATH)
        return []
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


def _coerce_page_entries(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(stripped)
            except (ValueError, SyntaxError):
                parsed = [{"page_number": 1, "text": stripped}]
        return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []
    return []


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


def _chunk_text(text: str) -> list[str]:
    compact = _normalize_text(text)
    if not compact:
        return []

    chunks: list[str] = []
    start = 0
    size = _chunk_size()
    overlap = _chunk_overlap()
    while start < len(compact):
        end = min(start + size, len(compact))
        chunk = compact[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(compact):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _build_chatbot_documents() -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for source_index, row in enumerate(_load_dataset_rows(), start=1):
        source_name = _normalize_text(str(row.get("source") or f"source_{source_index}"))
        page_entries = _coerce_page_entries(row.get("content"))
        if not page_entries:
            page_entries = [{"page_number": 1, "text": _normalize_text(str(row.get("content") or "")), "tables": []}]

        for page_index, entry in enumerate(page_entries, start=1):
            page_number = entry.get("page_number") or page_index
            page_text = _cleanup_source_text(str(entry.get("text") or ""))
            table_text = "\n".join(
                _cleanup_source_text(flattened)
                for table in entry.get("tables", []) or []
                if (flattened := _flatten_table(table))
            )
            merged_text = _normalize_text("\n".join(part for part in (page_text, table_text) if part))
            for chunk_index, chunk in enumerate(_chunk_text(merged_text), start=1):
                documents.append(
                    {
                        "id": f"chatbot_{source_index:02d}_{page_index:04d}_{chunk_index:03d}",
                        "document": chunk,
                        "embedding": _embed_text(chunk),
                        "metadata": {
                            "source": source_name,
                            "page_number": int(page_number) if str(page_number).isdigit() else page_index,
                            "chunk_index": chunk_index,
                        },
                    }
                )
    return documents


def _create_client() -> chromadb.PersistentClient:
    CHATBOT_CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHATBOT_CHROMA_DIR))


def _ensure_chatbot_collection() -> chromadb.api.models.Collection.Collection:
    client = _create_client()

    with _BUILD_LOCK:
        needs_rebuild = not _manifest_is_current()
        try:
            collection = client.get_collection(CHATBOT_COLLECTION_NAME)
            if collection.count() == 0:
                needs_rebuild = True
        except (ValueError, NotFoundError):
            collection = None
            needs_rebuild = True

        if not needs_rebuild and collection is not None:
            return collection

        if collection is not None:
            try:
                client.delete_collection(CHATBOT_COLLECTION_NAME)
            except (ValueError, NotFoundError):
                pass

        collection = client.create_collection(
            name=CHATBOT_COLLECTION_NAME,
            metadata={"description": "Local designer support chatbot corpus"},
        )
        documents = _build_chatbot_documents()
        if not documents:
            return collection

        batch_size = 200
        for start in range(0, len(documents), batch_size):
            batch = documents[start : start + batch_size]
            collection.add(
                ids=[item["id"] for item in batch],
                documents=[item["document"] for item in batch],
                embeddings=[item["embedding"] for item in batch],
                metadatas=[item["metadata"] for item in batch],
            )
        _write_manifest()
        logger.info("[local_chatbot_index_ready] path=%s documents=%s", CHATBOT_CHROMA_DIR, len(documents))
        return collection


def ensure_local_chatbot_index() -> int:
    return _ensure_chatbot_collection().count()


def _lexical_matches(question: str, *, limit: int) -> list[dict[str, Any]]:
    question_tokens = _normalize_tokens(question)
    scored_matches: list[dict[str, Any]] = []
    for item in _build_chatbot_documents():
        document = _cleanup_source_text(str(item["document"] or ""))
        metadata = item["metadata"]
        if len(document) < 20 or _is_noisy_document(document):
            continue
        overlap = len(question_tokens & _normalize_tokens(document))
        if overlap <= 0:
            continue
        document_penalty = _document_penalty(document)
        scored_matches.append(
            {
                "document": document,
                "metadata": metadata,
                "score": float(overlap),
                "rank_bonus": document_penalty,
            }
        )
    scored_matches.sort(key=lambda item: (item.get("rank_bonus", 0), item["score"]), reverse=True)
    return scored_matches[:limit]


def retrieve_local_chatbot_matches(question: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    normalized_question = _normalize_text(question)
    if not normalized_question:
        return []

    limit = limit or _chatbot_top_k()
    question_tokens = _normalize_tokens(normalized_question)
    try:
        collection = _ensure_chatbot_collection()
        payload = collection.query(
            query_embeddings=[_embed_text(normalized_question)],
            n_results=max(limit * 4, 8),
            include=["documents", "metadatas", "distances"],
        )
        documents = (payload.get("documents") or [[]])[0]
        metadatas = (payload.get("metadatas") or [[]])[0]
        distances = (payload.get("distances") or [[]])[0]
        matches_by_key: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
        for document, metadata, distance in zip(documents, metadatas, distances):
            if not isinstance(metadata, dict):
                continue
            doc_text = _cleanup_source_text(str(document or ""))
            if len(doc_text) < 20 or _is_noisy_document(doc_text):
                continue
            lexical_overlap = len(question_tokens & _normalize_tokens(doc_text))
            source_score = _source_bonus_for_question(
                normalized_question,
                str(metadata.get("source") or ""),
            ) + _source_penalty_for_question(normalized_question, str(metadata.get("source") or ""))
            content_bonus = _content_bonus_for_question(normalized_question, doc_text)
            rank_bonus = content_bonus + _document_penalty(doc_text)
            key = (
                metadata.get("source"),
                metadata.get("page_number"),
                metadata.get("chunk_index"),
            )
            matches_by_key[key] = {
                "document": doc_text,
                "metadata": metadata,
                "score": min(1.0, max(0.0, 1.0 - float(distance or 0.0))),
                "lexical_overlap": lexical_overlap,
                "source_score": source_score,
                "content_bonus": content_bonus,
                "rank_bonus": rank_bonus,
            }

        for lexical_match in _lexical_matches(normalized_question, limit=max(limit * 2, 8)):
            metadata = lexical_match.get("metadata", {})
            key = (
                metadata.get("source"),
                metadata.get("page_number"),
                metadata.get("chunk_index"),
            )
            existing = matches_by_key.get(key)
            if existing is None:
                document = _cleanup_source_text(str(lexical_match.get("document") or ""))
                matches_by_key[key] = {
                    **lexical_match,
                    "document": document,
                    "lexical_overlap": int(lexical_match.get("score") or 0.0),
                    "source_score": _source_bonus_for_question(
                        normalized_question,
                        str(metadata.get("source") or ""),
                    ) + _source_penalty_for_question(normalized_question, str(metadata.get("source") or "")),
                    "content_bonus": _content_bonus_for_question(normalized_question, document),
                    "rank_bonus": _content_bonus_for_question(normalized_question, document)
                    + _document_penalty(document),
                }
                continue
            existing["lexical_overlap"] = max(
                int(existing.get("lexical_overlap") or 0),
                int(lexical_match.get("score") or 0.0),
            )
            existing["source_score"] = max(
                int(existing.get("source_score") or 0),
                _source_bonus_for_question(normalized_question, str(metadata.get("source") or ""))
                + _source_penalty_for_question(normalized_question, str(metadata.get("source") or "")),
            )
            existing["content_bonus"] = max(
                int(existing.get("content_bonus") or 0),
                _content_bonus_for_question(normalized_question, str(existing.get("document") or "")),
            )
            existing["rank_bonus"] = max(
                int(existing.get("rank_bonus") or 0),
                int(existing.get("content_bonus") or 0)
                + _document_penalty(str(existing.get("document") or "")),
            )

        matches = list(matches_by_key.values())
        matches.sort(
            key=lambda item: (
                -int(item.get("rank_bonus") or 0),
                -int(item.get("lexical_overlap") or 0),
                -int(item.get("source_score") or 0),
                -float(item.get("score") or 0.0),
            )
        )
        if any(int(item.get("lexical_overlap") or 0) > 0 for item in matches):
            matches = [item for item in matches if int(item.get("lexical_overlap") or 0) > 0]
        if matches:
            return matches[:limit]
    except Exception as exc:
        logger.warning("[local_chatbot_chroma_unavailable] reason=%s", exc)

    return _lexical_matches(normalized_question, limit=limit)


def _excerpt(value: str, *, limit: int = 220) -> str:
    text = _cleanup_source_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _clean_support_sentence(value: str) -> str:
    cleaned = _cleanup_source_text(value)
    cleaned = LEADING_STEP_PATTERN.sub("", cleaned)
    cleaned = NOISY_PREFIX_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"^(?:[-•·▶]\s*)+", "", cleaned)
    cleaned = re.sub(r"^(?:와 같이|과 같이)\s*", "", cleaned)
    cleaned = re.sub(r"^(?:추가로|또는)\s*", "", cleaned)
    return _normalize_text(cleaned)


def _shorten_for_chat(text: str, *, limit: int) -> str:
    cleaned = _normalize_text(text)
    if len(cleaned) <= limit:
        return cleaned

    comma_index = cleaned.rfind(",", 0, limit)
    if comma_index >= max(24, int(limit * 0.5)):
        return cleaned[:comma_index].rstrip(" ,") + " 등을 참고해 주세요"

    space_index = cleaned.rfind(" ", 0, limit)
    if space_index >= max(24, int(limit * 0.7)):
        return cleaned[:space_index].rstrip(" ,") + "..."

    return cleaned[: limit - 3].rstrip() + "..."


def _is_noisy_clause(value: str) -> bool:
    normalized = _normalize_text(value)
    if "출처:" in normalized:
        return True
    if any(keyword in normalized for keyword in NOISY_CLAUSE_KEYWORDS):
        return True
    if any(keyword in normalized for keyword in LOW_VALUE_DOCUMENT_KEYWORDS):
        return True
    if normalized.count(",") >= 6:
        return True
    return normalized.count(" - ") >= 2


def _extract_support_sentences(question: str, matches: list[dict[str, Any]]) -> list[str]:
    question_tokens = _normalize_tokens(question)
    normalized_question = _canonicalize_search_terms(question)
    best_source_score = max((int(match.get("source_score") or 0) for match in matches), default=0)
    candidate_sentences: list[tuple[int, int, int, str]] = []
    for match in matches[: max(2, _chatbot_top_k())]:
        match_source_score = int(match.get("source_score") or 0)
        match_rank_bonus = int(match.get("rank_bonus") or 0)
        if match_source_score < 0 and best_source_score >= 0:
            continue
        sentences = re.split(r"(?:[.!?。]+\s+|\n+)", str(match.get("document") or ""))
        for sentence in sentences:
            cleaned = _clean_support_sentence(sentence)
            if len(cleaned) < 20:
                continue
            if _is_noisy_clause(cleaned):
                continue
            if "가발" in cleaned and "가발" not in normalized_question:
                continue
            if len(cleaned) > 110:
                continue
            overlap = len(question_tokens & _normalize_tokens(cleaned))
            if overlap <= 0:
                continue
            sentence_bonus = _content_bonus_for_question(question, cleaned)
            candidate_sentences.append((match_rank_bonus + sentence_bonus, overlap, match_source_score, cleaned))

    candidate_sentences.sort(key=lambda item: (-item[0], -item[1], -item[2], len(item[3])))
    selected: list[str] = []
    seen: set[str] = set()
    for _, _, _, sentence in candidate_sentences:
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        selected.append(sentence)
        if len(selected) >= 2:
            break
    return selected


def _format_local_reply_section(title: str, items: list[str]) -> str:
    cleaned_items = [_normalize_text(item) for item in items if _normalize_text(item)]
    if not cleaned_items:
        return ""
    return title + ":\n" + "\n".join(f"- {item}" for item in cleaned_items)


def _ensure_reply_sentence(text: str) -> str:
    cleaned = _shorten_for_chat(text, limit=110)
    if not cleaned:
        return ""
    if cleaned[-1] in ".!?":
        return cleaned
    return cleaned + "."


def _is_greeting_message(question: str) -> bool:
    normalized = _normalize_text(question)
    if not normalized:
        return False
    lowered = normalized.lower()
    return any(keyword in lowered for keyword in GREETING_KEYWORDS + THANKS_KEYWORDS)


def _is_greeting_or_smalltalk(question: str) -> bool:
    normalized = _normalize_text(question)
    if not normalized:
        return False
    token_count = len(normalized.split())
    return _is_greeting_message(normalized) or token_count <= 1


def _build_smalltalk_reply(question: str) -> str:
    normalized = _normalize_text(question)
    lowered = normalized.lower()
    if any(keyword in lowered for keyword in THANKS_KEYWORDS):
        return "도움이 되셨다면 다행입니다. 이어서 필요한 시술 가이드는 강사처럼 실무 기준으로 차분히 정리해드릴게요."
    if any(keyword in lowered for keyword in GREETING_KEYWORDS):
        return (
            "안녕하세요. 실무 수업에서 짚어드리듯 핵심부터 자연스럽게 정리해드릴게요.\n"
            "원하는 시술명이나 현재 모발 상태를 함께 적어 주시면 더 정확하게 안내할 수 있습니다.\n"
            "예: 레이어드 컷 커트선 가이드 알려줘 / 염색 전 주의사항 알려줘"
        )
    return (
        "질문을 조금만 더 구체적으로 적어 주시면 강사처럼 핵심부터 차분하게 정리해드릴게요.\n"
        "예: 원하는 시술명, 현재 모발 상태, 최근 시술 이력을 함께 적어 주세요."
    )


def _guide_section_title(question: str) -> str:
    normalized_question = _canonicalize_search_terms(question)
    if any(keyword in normalized_question for keyword in CAUTION_QUERY_KEYWORDS):
        return "실무 기준으로 먼저 짚어드리면"
    return "강사처럼 핵심부터 말씀드리면"


def _build_check_items(question: str) -> list[str]:
    normalized_question = _canonicalize_search_terms(question)
    if any(keyword in normalized_question for keyword in CAUTION_QUERY_KEYWORDS):
        return [
            "두피 민감도와 알레르기 이력",
            "현재 모발 손상도와 최근 화학 시술 여부",
            "패치 테스트 가능 여부와 시술 전 두피 상태",
        ]
    return [
        "고객 모발 손상도와 현재 질감",
        "최근 시술 이력과 현재 스타일 유지 상태",
        "현장 상담 후 최종 적용 가능 여부",
    ]


def _build_match_based_fallback(match: dict[str, Any], *, question: str) -> str:
    source = _normalize_text(str(match.get("metadata", {}).get("source") or "로컬 상담 자료"))
    snippet = _cleanup_source_text(str(match.get("document") or ""))
    snippet = LEADING_STEP_PATTERN.sub("", snippet)
    snippet = NOISY_PREFIX_PATTERN.sub("", snippet)
    guide_title = _guide_section_title(question)
    check_items = _build_check_items(question)
    clauses = _extract_relevant_clauses(snippet, question=question)
    if clauses:
        return "\n\n".join(
            filter(
                None,
                [
                    _format_local_reply_section(guide_title, [_ensure_reply_sentence(item) for item in clauses]),
                    _format_local_reply_section(
                        "시술 전에 꼭 체크하세요",
                        check_items,
                    ),
                ],
            )
        )

    if len(snippet) > 140:
        snippet = snippet[:137].rstrip() + "..."
    if not snippet:
        return (
            f"{source} 기준으로 관련 자료는 찾았지만, 바로 고객 상담 문장으로 옮기기에는 정보가 조금 부족했습니다.\n\n"
            + _format_local_reply_section(
                "시술 전에 꼭 체크하세요",
                check_items,
            )
        )
    return "\n\n".join(
        filter(
            None,
            [
                _format_local_reply_section(guide_title, [_ensure_reply_sentence(snippet)]),
                _format_local_reply_section(
                    "시술 전에 꼭 체크하세요",
                    check_items,
                ),
            ],
        )
    )


def _extract_relevant_clauses(text: str, *, question: str, limit: int = 2) -> list[str]:
    question_tokens = _normalize_tokens(question)
    clauses: list[tuple[int, str]] = []
    for raw in re.split(r"(?:[.!?。]+\s+|\s+-\s+|\|\s+|\n+)", text):
        cleaned = _clean_support_sentence(raw)
        if _is_noisy_clause(cleaned):
            continue
        if len(cleaned) > 90:
            cleaned = _shorten_for_chat(cleaned, limit=90)
        if 16 <= len(cleaned) <= 90:
            overlap = len(question_tokens & _normalize_tokens(cleaned))
            clauses.append((overlap, cleaned))

    selected: list[str] = []
    seen: set[str] = set()
    clauses.sort(key=lambda item: (-item[0], len(item[1])))
    for overlap, clause in clauses:
        if not selected and overlap <= 0 and question_tokens:
            continue
        key = clause.lower()
        if key in seen:
            continue
        seen.add(key)
        selected.append(clause)
        if len(selected) >= limit:
            break
    return selected


def _compose_structured_local_reply(
    *,
    question: str,
    matches: list[dict[str, Any]],
    admin_name: str | None,
    store_name: str | None,
) -> str:
    del admin_name, store_name
    guide_title = _guide_section_title(question)
    common_check_items = _build_check_items(question)

    if not matches:
        if _is_greeting_or_smalltalk(question):
            return _build_smalltalk_reply(question)
        return (
            "지금 질문만으로는 바로 연결되는 실무 가이드를 찾기 어려웠습니다.\n"
            "원하는 시술명, 현재 모발 상태, 최근 시술 이력을 함께 적어 주시면 강사처럼 핵심부터 다시 정리해드릴게요.\n"
            "예: 레이어드 컷 커트선 가이드 알려줘 / 염색 전 주의사항 알려줘"
        )

    sentences = _extract_support_sentences(question, matches)
    if not sentences:
        return _build_match_based_fallback(matches[0], question=question)

    guide_items = [_ensure_reply_sentence(sentence) for sentence in sentences[:2]]
    return "\n\n".join(
        filter(
            None,
            [
                _format_local_reply_section(guide_title, guide_items),
                _format_local_reply_section("시술 전에 꼭 체크하세요", common_check_items),
            ],
        )
    )


def build_local_chatbot_reply(
    *,
    message: str,
    admin_name: str | None = None,
    store_name: str | None = None,
) -> dict[str, Any]:
    if _is_greeting_message(message):
        reply = _build_smalltalk_reply(message)
        return {
            "status": "success",
            "reply": reply,
            "timestamp": timezone.now().isoformat(),
            "matched_sources": [],
            "dataset_source": "local_chromadb_chatbot",
            "provider": "local_chromadb",
        }

    matches = retrieve_local_chatbot_matches(message, limit=_chatbot_top_k())
    reply = _compose_structured_local_reply(
        question=message,
        matches=matches,
        admin_name=admin_name,
        store_name=store_name,
    )
    return {
        "status": "success",
        "reply": reply,
        "timestamp": timezone.now().isoformat(),
        "matched_sources": [
            {
                "source": match.get("metadata", {}).get("source"),
                "page_number": match.get("metadata", {}).get("page_number"),
                "chunk_index": match.get("metadata", {}).get("chunk_index"),
                "score": round(float(match.get("score") or 0.0), 4),
                "excerpt": _excerpt(str(match.get("document") or "")),
            }
            for match in matches
        ],
        "dataset_source": "local_chromadb_chatbot",
        "provider": "local_chromadb",
    }


def get_local_chatbot_status() -> dict[str, Any]:
    dataset_exists = CHATBOT_DATASET_PATH.exists()
    collection_exists = CHATBOT_CHROMA_DIR.exists()
    document_count = None
    try:
        if collection_exists:
            client = _create_client()
            collection = client.get_collection(CHATBOT_COLLECTION_NAME)
            document_count = collection.count()
    except Exception:
        document_count = None

    return {
        "provider": "local_chromadb",
        "dataset_path": str(CHATBOT_DATASET_PATH),
        "dataset_exists": dataset_exists,
        "store_path": str(CHATBOT_CHROMA_DIR),
        "collection_name": CHATBOT_COLLECTION_NAME,
        "collection_ready": bool(document_count),
        "document_count": document_count,
        "manifest_current": _manifest_is_current(),
        "embedding_version": EMBEDDING_VERSION,
        "embedding_dim": _embedding_dim(),
    }
