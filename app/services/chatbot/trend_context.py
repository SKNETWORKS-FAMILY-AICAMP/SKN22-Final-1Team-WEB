from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.trend_pipeline.latest_feed import get_latest_crawled_trends


DEFAULT_TREND_LIMIT = 8
KOREAN_SUFFIXES = (
    "으로",
    "에서",
    "에게",
    "한테",
    "께서",
    "까지",
    "부터",
    "처럼",
    "같이",
    "이라도",
    "라도",
    "이나",
    "나",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "에",
    "와",
    "과",
    "도",
    "로",
    "랑",
    "이랑",
)
QUERY_STOPWORDS = {
    "뭐",
    "뭐야",
    "무엇",
    "알려줘",
    "알려",
    "말해줘",
    "말해",
    "설명해줘",
    "설명",
    "추천해줘",
    "추천",
    "스타일",
    "헤어",
    "룩",
    "한",
    "했던",
    "하는",
    "어떤",
    "이거",
    "저거",
    "지금",
    "최근",
}
ENTITY_ALIASES = {
    "캣츠아이": {"katseye"},
    "katseye": {"캣츠아이"},
    "가브리엘": {"gabrielle"},
    "유니온": {"union"},
    "가브리엘 유니온": {"gabrielle union"},
    "gabrielle union": {"가브리엘 유니온"},
}


def _normalize_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).lower()
    normalized = re.sub(r"[^0-9a-z가-힣\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _contains_term(haystack: str, term: str) -> bool:
    if not haystack or not term:
        return False
    if re.search(r"[a-z]", term):
        pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
        return bool(re.search(pattern, haystack))
    return term in haystack


def _strip_korean_suffixes(token: str) -> set[str]:
    variants = {token}
    for suffix in KOREAN_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 2:
            variants.add(token[: -len(suffix)])
    return {variant for variant in variants if variant}


def _expand_token(token: str) -> set[str]:
    variants = set()
    for variant in _strip_korean_suffixes(token):
        variants.add(variant)
        variants.update(ENTITY_ALIASES.get(variant, set()))
    return {variant for variant in variants if variant and variant not in QUERY_STOPWORDS}


def _build_query_terms(value: str | None) -> list[str]:
    normalized = _normalize_text(value)
    if not normalized:
        return []

    terms: list[str] = []
    seen: set[str] = set()
    for token in normalized.split(" "):
        if len(token) < 2:
            continue
        for variant in _expand_token(token):
            if variant in seen:
                continue
            seen.add(variant)
            terms.append(variant)

    for phrase, aliases in ENTITY_ALIASES.items():
        if _contains_term(normalized, phrase):
            if phrase not in seen:
                seen.add(phrase)
                terms.append(phrase)
            for alias in aliases:
                if alias not in seen:
                    seen.add(alias)
                    terms.append(alias)

    return terms


def _score_item(item: dict[str, Any], query_terms: list[str]) -> int:
    title = _normalize_text(item.get("title_ko") or item.get("title"))
    summary = _normalize_text(item.get("summary_ko") or item.get("summary"))
    source = _normalize_text(item.get("source_name") or item.get("source"))
    keywords = [_normalize_text(keyword) for keyword in list(item.get("keywords") or [])]
    keyword_blob = " ".join(keyword for keyword in keywords if keyword)
    article_url = _normalize_text(item.get("article_url"))

    score = 0
    for term in query_terms:
        if not term:
            continue
        if _contains_term(title, term):
            score += 10
        if keyword_blob and _contains_term(keyword_blob, term):
            score += 7
        if summary and _contains_term(summary, term):
            score += 4
        if source and _contains_term(source, term):
            score += 2
        if article_url and _contains_term(article_url, term):
            score += 2
    return score


def build_customer_trend_context(
    *,
    message: str,
    limit: int = DEFAULT_TREND_LIMIT,
) -> dict[str, Any]:
    question = str(message or "").strip()
    payload = get_latest_crawled_trends(limit=max(5, limit))
    items = [item for item in payload.get("items") or [] if isinstance(item, dict)]
    query_terms = _build_query_terms(question)

    if query_terms:
        ranked = sorted(
            items,
            key=lambda item: (
                -_score_item(item, query_terms),
                str(item.get("published_at") or ""),
                str(item.get("crawled_at") or ""),
            ),
        )
    else:
        ranked = list(items)

    selected = ranked[: max(3, min(limit, len(ranked)))]

    source_context_parts: list[str] = []
    matched_sources: list[dict[str, Any]] = []
    for index, item in enumerate(selected, start=1):
        keywords = [keyword for keyword in list(item.get("keywords") or []) if keyword]
        source_context_parts.append(
            "\n".join(
                [
                    f"[트렌드 {index}]",
                    f"제목: {str(item.get('title_ko') or item.get('title') or '').strip()}",
                    f"요약: {str(item.get('summary_ko') or item.get('summary') or '').strip()}",
                    f"키워드: {', '.join(keywords)}",
                    f"출처: {str(item.get('source_name') or item.get('source') or '').strip()}",
                ]
            )
        )
        matched_sources.append(
            {
                "title": str(item.get("title_ko") or item.get("title") or "").strip(),
                "source": str(item.get("source_name") or item.get("source") or "").strip(),
                "article_url": item.get("article_url"),
                "image_url": item.get("image_url"),
                "keywords": keywords,
            }
        )

    return {
        "search_query": question,
        "matched_sources": matched_sources,
        "source_context": "\n\n".join(source_context_parts).strip(),
        "dataset_source": "latest_trend_feed",
        "provider": "trend_feed",
    }
