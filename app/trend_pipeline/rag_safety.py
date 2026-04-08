from __future__ import annotations

import re
from typing import Any


_TITLE_NOISE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("newsletter", re.compile(r"\bnewsletter\b", re.IGNORECASE)),
    ("subscribe", re.compile(r"\bsubscribe\b", re.IGNORECASE)),
    ("shop", re.compile(r"\bshop(?:\s+now)?\b", re.IGNORECASE)),
    ("advertisement", re.compile(r"\badvert(?:isement|orial)?\b", re.IGNORECASE)),
    ("sponsored", re.compile(r"\bsponsored\b", re.IGNORECASE)),
    ("paid_partnership", re.compile(r"\bpaid partnership\b", re.IGNORECASE)),
    ("ad_choices", re.compile(r"\bad choices?\b", re.IGNORECASE)),
)

_BODY_NOISE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("newsletter_signup", re.compile(r"\bsign up\b.*\bnewsletter\b", re.IGNORECASE)),
    ("newsletter_subscribe", re.compile(r"\bsubscribe\b.*\bnewsletter\b", re.IGNORECASE)),
    ("shop_now", re.compile(r"\bshop now\b", re.IGNORECASE)),
    ("advertisement", re.compile(r"\badvert(?:isement|orial)?\b", re.IGNORECASE)),
    ("sponsored", re.compile(r"\bsponsored\b", re.IGNORECASE)),
    ("paid_partnership", re.compile(r"\bpaid partnership\b", re.IGNORECASE)),
    ("affiliate", re.compile(r"\baffiliate\b", re.IGNORECASE)),
    ("ad_choices", re.compile(r"\bad choices?\b", re.IGNORECASE)),
)


def sanitize_rag_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sanitized_items: list[dict[str, Any]] = []
    retitled_count = 0
    dropped_count = 0
    rewritten_examples: list[dict[str, Any]] = []
    dropped_examples: list[dict[str, Any]] = []

    for item in items:
        sanitized_item, action = sanitize_rag_item(item)
        if sanitized_item is None:
            dropped_count += 1
            if action is not None and len(dropped_examples) < 5:
                dropped_examples.append(action)
            continue

        sanitized_items.append(sanitized_item)
        if action is not None and action.get("action") == "retitle":
            retitled_count += 1
            if len(rewritten_examples) < 5:
                rewritten_examples.append(action)

    report = {
        "input_count": len(items),
        "output_count": len(sanitized_items),
        "retitled_count": retitled_count,
        "dropped_count": dropped_count,
        "retitled_examples": rewritten_examples,
        "dropped_examples": dropped_examples,
    }
    return sanitized_items, report


def sanitize_rag_item(item: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    row = dict(item)
    display_title = _clean_text(row.get("display_title") or row.get("title"))
    article_title = _clean_text(row.get("article_title"))
    title_reasons = _matched_labels(f"{display_title}\n{article_title}", _TITLE_NOISE_PATTERNS)
    body_reasons = _matched_labels(_joined_body_text(row), _BODY_NOISE_PATTERNS)
    has_trend_signal = _has_trend_signal(row)

    if title_reasons:
        fallback_title = _fallback_title(row)
        if has_trend_signal and fallback_title:
            original_title = display_title or article_title
            row["display_title"] = fallback_title
            if article_title and article_title != fallback_title:
                row["article_title"] = fallback_title
            return row, {
                "action": "retitle",
                "from": original_title,
                "to": fallback_title,
                "reason": ", ".join(title_reasons),
            }

        return None, {
            "action": "drop",
            "title": display_title or article_title,
            "reason": ", ".join(title_reasons),
        }

    if len(body_reasons) >= 2 and not has_trend_signal:
        return None, {
            "action": "drop",
            "title": display_title or article_title or _fallback_title(row),
            "reason": ", ".join(body_reasons),
        }

    if not display_title:
        fallback_title = _fallback_title(row)
        if fallback_title:
            row["display_title"] = fallback_title

    return row, None


def _has_trend_signal(item: dict[str, Any]) -> bool:
    canonical_name = _clean_text(item.get("canonical_name"))
    if canonical_name:
        return True

    for field in ("style_tags", "color_tags"):
        values = item.get(field)
        if isinstance(values, list) and any(_clean_text(value) for value in values):
            return True

    summary = _clean_text(item.get("summary"))
    search_text = _clean_text(item.get("search_text"))
    return len(summary) >= 24 or len(search_text) >= 24


def _fallback_title(item: dict[str, Any]) -> str:
    for raw_value in (
        item.get("display_title"),
        item.get("title"),
        item.get("article_title"),
    ):
        candidate = _clean_text(raw_value)
        if candidate and not _matched_labels(candidate, _TITLE_NOISE_PATTERNS):
            return candidate

    canonical_name = _clean_text(item.get("canonical_name"))
    if canonical_name:
        return _humanize_label(canonical_name)

    search_text = _clean_text(item.get("search_text"))
    if search_text:
        first_chunk = search_text.split(",")[0].strip()
        if first_chunk and not _matched_labels(first_chunk, _TITLE_NOISE_PATTERNS):
            return _humanize_label(first_chunk)

    for field in ("style_tags", "color_tags"):
        values = item.get(field)
        if isinstance(values, list):
            cleaned_values = [_clean_text(value) for value in values if _clean_text(value)]
            if cleaned_values:
                return _humanize_label(cleaned_values[0])

    return ""


def _humanize_label(value: str) -> str:
    normalized = re.sub(r"[_-]+", " ", value).strip()
    if not normalized:
        return ""

    return re.sub(r"[A-Za-z]+('[A-Za-z]+)?", _title_case_match, normalized)


def _title_case_match(match: re.Match[str]) -> str:
    word = match.group(0)
    if "'" not in word:
        return word.capitalize()

    head, tail = word.split("'", 1)
    if tail.lower() == "s":
        return f"{head.capitalize()}'s"
    return f"{head.capitalize()}'{tail.capitalize()}"


def _joined_body_text(item: dict[str, Any]) -> str:
    parts = [
        _clean_text(item.get("summary")),
        _clean_text(item.get("search_text")),
        _clean_text(item.get("article_title")),
        _clean_text(item.get("article_url")),
        _clean_text(item.get("source")),
    ]
    return "\n".join(part for part in parts if part)


def _matched_labels(text: str, patterns: tuple[tuple[str, re.Pattern[str]], ...]) -> list[str]:
    if not text:
        return []
    return [label for label, pattern in patterns if pattern.search(text)]


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()
