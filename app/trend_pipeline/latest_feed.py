from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .chroma_client import create_persistent_client
from .paths import CHROMA_TRENDS_DIR, TREND_PROCESSED_DIR, TREND_RAW_DIR

try:
    from django.conf import settings as django_settings
except Exception:  # pragma: no cover - standalone script path
    django_settings = None


REFINED_TRENDS_FILE = TREND_PROCESSED_DIR / "refined_trends.json"
TRANSLATION_CACHE_FILE = TREND_PROCESSED_DIR / "latest_trend_translations.json"
DEFAULT_TRANSLATION_MODEL = "gemini-2.5-flash"
CHROMA_COLLECTION_NAME = "hair_trends"
DEFAULT_RUNPOD_LATEST_TIMEOUT = 8
DEFAULT_RUNPOD_LATEST_POLL_INTERVAL = 2.0

PUBLICATION_HOST_MAP = {
    "allure.com": "Allure",
    "byrdie.com": "Byrdie",
    "cosmopolitan.com": "Cosmopolitan",
    "elle.com": "ELLE",
    "glamour.com": "Glamour",
    "harpersbazaar.com": "Harper's Bazaar",
    "instyle.com": "InStyle",
    "marieclaire.com": "Marie Claire",
    "newbeauty.com": "NewBeauty",
    "oprahdaily.com": "Oprah Daily",
    "people.com": "People",
    "popsugar.com": "POPSUGAR",
    "refinery29.com": "Refinery29",
    "teenvogue.com": "Teen Vogue",
    "thezoereport.com": "The Zoe Report",
    "vogue.com": "Vogue",
    "whowhatwear.com": "Who What Wear",
    "wmagazine.com": "W Magazine",
}

PUBLICATION_SOURCE_MAP = {
    "allure": "Allure",
    "byrdie": "Byrdie",
    "cosmopolitan": "Cosmopolitan",
    "elle": "ELLE",
    "glamour": "Glamour",
    "harpersbazaar": "Harper's Bazaar",
    "instyle": "InStyle",
    "marieclaire": "Marie Claire",
    "newbeauty": "NewBeauty",
    "oprahdaily": "Oprah Daily",
    "people": "People",
    "popsugar": "POPSUGAR",
    "refinery29": "Refinery29",
    "teenvogue": "Teen Vogue",
    "thezoereport": "The Zoe Report",
    "vogue": "Vogue",
    "whowhatwear": "Who What Wear",
    "wmagazine": "W Magazine",
}

STYLE_INCLUDE_KEYWORDS = (
    "hairstyle",
    "haircut",
    "hair color",
    "hair-color",
    "hair trend",
    "bang",
    "bangs",
    "fringe",
    "bob",
    "pixie",
    "mullet",
    "lob",
    "layered cut",
    "layers",
    "braid",
    "braids",
    "ponytail",
    "bun",
    "updo",
    "perm",
    "curl",
    "curls",
    "wave",
    "waves",
    "blowout",
    "shag",
    "big chop",
    "dip-dye",
    "ombre",
    "balayage",
    "highlight",
    "highlights",
    "blonde",
    "blond",
    "brunette",
    "red hair",
    "copper hair",
    "pink hair",
    "silver hair",
    "celeb hair",
    "hair makeover",
    "헤어스타일",
    "헤어 스타일",
    "머리 스타일",
    "헤어컷",
    "커트",
    "컷",
    "단발",
    "보브",
    "픽시",
    "앞머리",
    "뱅",
    "브레이드",
    "포니테일",
    "업두",
    "펌",
    "웨이브",
    "염색",
    "탈색",
    "옴브레",
    "발레아쥬",
    "레이어드",
    "숏컷",
    "롱헤어",
)

STYLE_EXCLUDE_KEYWORDS = (
    "skin-care",
    "skincare",
    "skin care",
    "routine",
    "cleanser",
    "serum",
    "essence",
    "cream",
    "moisturizer",
    "sunscreen",
    "shampoo",
    "conditioner",
    "mask",
    "treatment",
    "primer",
    "spray",
    "mousse",
    "gel",
    "wax",
    "pomade",
    "dryer",
    "iron",
    "roller",
    "rollers",
    "tool",
    "brush",
    "scalp",
    "health",
    "supplement",
    "product",
    "products",
    "shopping",
    "review",
    "reviews",
    "best of beauty",
    "worth it",
    "price",
    "amazon",
    "korean skin-care",
    "korean skincare",
    "두피",
    "샴푸",
    "컨디셔너",
    "트리트먼트",
    "제품",
    "상품",
    "리뷰",
)

STYLE_URL_KEYWORDS = (
    "hairstyle",
    "haircut",
    "hair-color",
    "hair-color",
    "hair-trend",
    "hair-trends",
    "bob",
    "pixie",
    "mullet",
    "lob",
    "bang",
    "bangs",
    "fringe",
    "braid",
    "ponytail",
    "updo",
    "perm",
    "curl",
    "wave",
    "blonde",
    "brunette",
    "copper",
    "ombre",
    "balayage",
    "big-chop",
)

KEYWORD_LABEL_MAP = {
    "big chop": "빅 찹",
    "french bob": "프렌치 보브",
    "bob": "보브",
    "bangs": "앞머리",
    "bang": "앞머리",
    "fringe": "앞머리",
    "brunette": "브루넷",
    "copper": "코퍼",
    "bronze": "브론즈",
    "blonde": "블론드",
    "red hair": "레드 헤어",
    "brown": "브라운",
    "pixie": "픽시",
    "mullet": "멀릿",
    "lob": "롱 보브",
    "layered": "레이어드",
    "layers": "레이어드",
    "wave": "웨이브",
    "waves": "웨이브",
    "curl": "컬",
    "curls": "컬",
    "ombre": "옴브레",
    "balayage": "발레아주",
    "updo": "업두",
    "ponytail": "포니테일",
    "braid": "브레이드",
    "braids": "브레이드",
    "perm": "펌",
    "hair color": "헤어 컬러",
}

DERIVED_KEYWORD_PATTERNS = (
    (r"(?<![a-z])french bob(?![a-z])", "프렌치 보브"),
    (r"(?<![a-z])big chop(?![a-z])", "빅 찹"),
    (r"(?<![a-z])bangs?(?![a-z])", "앞머리"),
    (r"(?<![a-z])fringe(?![a-z])", "앞머리"),
    (r"(?<![a-z])brunette(?![a-z])", "브루넷"),
    (r"(?<![a-z])copper(?![a-z])", "코퍼"),
    (r"(?<![a-z])bronze(?![a-z])", "브론즈"),
    (r"(?<![a-z])bob(?![a-z])", "보브"),
    (r"(?<![a-z])pixie(?![a-z])", "픽시"),
    (r"(?<![a-z])mullet(?![a-z])", "멀릿"),
    (r"(?<![a-z])lob(?![a-z])", "롱 보브"),
    (r"(?<![a-z])layered(?![a-z])", "레이어드"),
    (r"(?<![a-z])waves?(?![a-z])", "웨이브"),
    (r"(?<![a-z])curls?(?![a-z])", "컬"),
    (r"(?<![a-z])ombre(?![a-z])", "옴브레"),
    (r"(?<![a-z])balayage(?![a-z])", "발레아주"),
    (r"(?<![a-z])updo(?![a-z])", "업두"),
    (r"(?<![a-z])ponytail(?![a-z])", "포니테일"),
    (r"(?<![a-z])braids?(?![a-z])", "브레이드"),
    (r"(?<![a-z])perm(?![a-z])", "펌"),
    (r"(?<![a-z])blonde(?![a-z])", "블론드"),
    (r"(?<![a-z])red hair(?![a-z])", "레드 헤어"),
    (r"(?<![a-z])hair color(?![a-z])", "헤어 컬러"),
)


def _get_django_setting(name: str, default: str = "") -> str:
    if django_settings is None:
        return default
    try:
        if getattr(django_settings, "configured", False):
            return str(getattr(django_settings, name, default))
    except Exception:
        return default
    return default


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _iter_raw_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(TREND_RAW_DIR.glob("*.json")):
        items.extend(_load_json_list(path))
    return items


def _iter_chroma_items() -> list[dict[str, Any]]:
    if not CHROMA_TRENDS_DIR.exists():
        return []

    try:
        client = create_persistent_client(CHROMA_TRENDS_DIR)
        collection = client.get_collection(CHROMA_COLLECTION_NAME)
        payload = collection.get(include=["metadatas"])
    except Exception:
        return []

    metadatas = payload.get("metadatas") if isinstance(payload, dict) else None
    if not isinstance(metadatas, list):
        return []

    items: list[dict[str, Any]] = []
    has_feed_metadata = False
    for metadata in metadatas:
        if not isinstance(metadata, dict):
            continue
        row = dict(metadata)
        if row.get("article_url") or row.get("image_url") or row.get("published_at") or row.get("crawled_at"):
            has_feed_metadata = True
        items.append(row)

    return items if has_feed_metadata else []


def _is_enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _runpod_latest_enabled() -> bool:
    return _is_enabled(
        os.environ.get("TREND_LATEST_REMOTE_ENABLED")
        or _get_django_setting("TREND_LATEST_REMOTE_ENABLED", "")
    )


def _runpod_latest_timeout() -> int:
    raw = os.environ.get("TREND_LATEST_RUNPOD_TIMEOUT") or _get_django_setting("TREND_LATEST_RUNPOD_TIMEOUT", "")
    try:
        return max(3, int(str(raw).strip()))
    except (TypeError, ValueError):
        return DEFAULT_RUNPOD_LATEST_TIMEOUT


def _runpod_latest_poll_interval() -> float:
    raw = os.environ.get("TREND_LATEST_RUNPOD_POLL_INTERVAL") or _get_django_setting("TREND_LATEST_RUNPOD_POLL_INTERVAL", "")
    try:
        return max(0.5, float(str(raw).strip()))
    except (TypeError, ValueError):
        return DEFAULT_RUNPOD_LATEST_POLL_INTERVAL


def _latest_trends_cache_seconds() -> int:
    raw = os.environ.get("LATEST_TRENDS_CACHE_SECONDS") or _get_django_setting("LATEST_TRENDS_CACHE_SECONDS", "60")
    try:
        return max(0, int(str(raw).strip()))
    except (TypeError, ValueError):
        return 60


def _latest_trends_cache_key(limit: int) -> str:
    prefix = os.environ.get("REDIS_KEY_PREFIX") or _get_django_setting("REDIS_KEY_PREFIX", "mirrai")
    normalized_prefix = str(prefix or "mirrai").strip() or "mirrai"
    remote_enabled = "1" if _runpod_latest_enabled() else "0"
    return f"{normalized_prefix}:cache:latest-trends:v1:limit:{int(limit)}:remote-enabled:{remote_enabled}"


def _get_latest_trends_cached(limit: int) -> dict[str, Any] | None:
    if _latest_trends_cache_seconds() <= 0:
        return None

    try:
        from app.services.runtime_cache import get_cached_payload

        payload = get_cached_payload(_latest_trends_cache_key(limit))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _set_latest_trends_cached(limit: int, payload: dict[str, Any]) -> dict[str, Any]:
    timeout = _latest_trends_cache_seconds()
    if timeout <= 0:
        return payload

    try:
        from app.services.runtime_cache import set_cached_payload

        set_cached_payload(_latest_trends_cache_key(limit), payload, timeout=timeout)
    except Exception:
        return payload
    return payload


def _source_slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _publication_name_from_url(article_url: Any) -> str:
    parsed = urlparse(str(article_url or "").strip())
    host = parsed.netloc.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return PUBLICATION_HOST_MAP.get(host, "")


def _display_source_name(*, source: Any, article_url: Any) -> str:
    source_name = _publication_name_from_url(article_url)
    if source_name:
        return source_name

    normalized = PUBLICATION_SOURCE_MAP.get(_source_slug(source))
    if normalized:
        return normalized

    cleaned = " ".join(str(source or "").split())
    if cleaned and cleaned.lower() != "unknown":
        return cleaned

    return "Unknown"


def _normalize_remote_item(item: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    title = str(item.get("title") or item.get("display_title") or item.get("article_title") or "").strip()
    if not title:
        return None

    article_url = str(item.get("article_url") or "").strip() or None
    source = str(item.get("source") or item.get("publisher") or item.get("publication") or "").strip() or "Unknown"

    return {
        "title": title,
        "summary": _compact_summary(item.get("summary") or item.get("description") or ""),
        "image_url": str(item.get("image_url") or "").strip() or None,
        "article_url": article_url,
        "source": source,
        "source_name": _display_source_name(source=source, article_url=article_url),
        "published_at": str(item.get("published_at") or "").strip() or None,
        "crawled_at": str(item.get("crawled_at") or "").strip() or None,
        "category": str(item.get("category") or "").strip() or "trend",
        "keywords": item.get("keywords") if isinstance(item.get("keywords"), list) else [],
        "title_ko": str(item.get("title_ko") or "").strip(),
        "summary_ko": str(item.get("summary_ko") or "").strip(),
    }


def _localize_items_preserving_existing(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if all(item.get("title_ko") and item.get("summary_ko") for item in items):
        return items

    to_translate = [
        {"title": item.get("title", ""), "summary": item.get("summary", ""), "article_url": item.get("article_url", "")}
        for item in items
        if not item.get("title_ko") or not item.get("summary_ko")
    ]
    translated_lookup: dict[str, dict[str, Any]] = {}
    if to_translate:
        translated_items = _attach_korean_fields(to_translate)
        translated_lookup = {
            _translation_cache_key(item): item
            for item in translated_items
        }

    localized: list[dict[str, Any]] = []
    for item in items:
        key = _translation_cache_key(item)
        translated = translated_lookup.get(key, {})
        localized.append(
            {
                **item,
                "title_ko": item.get("title_ko") or translated.get("title_ko") or item.get("title", ""),
                "summary_ko": item.get("summary_ko") or translated.get("summary_ko") or item.get("summary", ""),
            }
        )
    return localized


def _load_runpod_latest_trends(*, limit: int) -> dict[str, Any] | None:
    if not _runpod_latest_enabled():
        return None

    try:
        from app.services.trend_refresh import _submit_runpod_job
    except Exception:
        return None

    try:
        payload = _submit_runpod_job(
            request_input={"action": "latest_trends", "limit": max(1, min(int(limit), 5))},
            endpoint_id=None,
            api_key=None,
            base_url=None,
            sync=True,
            wait=True,
            timeout=_runpod_latest_timeout(),
            poll_interval=_runpod_latest_poll_interval(),
        )
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    items = payload.get("items")
    if not isinstance(items, list):
        data = payload.get("data")
        if isinstance(data, dict):
            items = data.get("items")
    if not isinstance(items, list):
        return None

    normalized_items = [normalized for row in items if (normalized := _normalize_remote_item(row)) is not None]
    localized_items = _localize_items_preserving_existing(normalized_items)
    return {
        "status": "ready",
        "source": "runpod_latest_trends",
        "count": len(localized_items),
        "items": localized_items[: max(1, min(int(limit), 5))],
    }


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _compact_summary(value: Any, *, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _looks_like_listing_url(value: str) -> bool:
    if not value:
        return True
    parsed = urlparse(value)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) < 3:
        return True
    last_segment = segments[-1].lower()
    generic_segments = {
        "beauty",
        "hair",
        "grooming",
        "style",
        "beauty-trend",
        "beauty-pictorial",
        "beauty-item",
        "news",
        "item",
        "pictorial",
    }
    return last_segment in generic_segments


def _contains_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    for keyword in keywords:
        needle = keyword.lower()
        if not needle:
            continue
        if re.search(r"[a-z]", needle):
            pattern = rf"(?<![a-z]){re.escape(needle)}(?![a-z])"
            if re.search(pattern, lowered):
                return True
            continue
        if needle in lowered:
            return True
    return False


def _append_keyword(keywords: list[str], label: str) -> None:
    cleaned = label.strip()
    if not cleaned:
        return
    if cleaned != "보브" and cleaned.endswith("보브"):
        keywords[:] = [existing for existing in keywords if existing != "보브"]
    if cleaned == "보브" and any("보브" in existing for existing in keywords):
        return
    if cleaned == "앞머리" and cleaned in keywords:
        return
    if cleaned not in keywords:
        keywords.append(cleaned)


def _split_keyword_tokens(value: Any) -> list[str]:
    if not value:
        return []
    return [token.strip().lower() for token in str(value).split(",") if token.strip()]


def _extract_keywords(item: dict[str, Any]) -> list[str]:
    evidence_parts = [
        str(item.get("trend_name") or ""),
        str(item.get("display_title") or ""),
        str(item.get("article_title") or ""),
        str(item.get("description") or item.get("summary") or item.get("search_text") or ""),
        str(item.get("article_url") or ""),
    ]
    evidence_text = " ".join(evidence_parts).lower()

    keywords: list[str] = []
    for raw_token in _split_keyword_tokens(item.get("hairstyle_text")) + _split_keyword_tokens(item.get("color_text")):
        label = KEYWORD_LABEL_MAP.get(raw_token)
        if not label:
            continue
        if _contains_any_keyword(evidence_text, (raw_token,)):
            _append_keyword(keywords, label)

    for pattern, label in DERIVED_KEYWORD_PATTERNS:
        if re.search(pattern, evidence_text):
            _append_keyword(keywords, label)

    return keywords[:2]


def _pick_display_title(item: dict[str, Any]) -> str:
    trend_title = str(item.get("trend_name") or item.get("display_title") or "").strip()
    article_title = str(item.get("article_title") or "").strip()

    generic_titles = {
        "vogue beauty",
        "more great beauty stories fromvogue",
        "more great beauty stories from vogue",
    }
    trend_title_lower = trend_title.lower()

    if not trend_title:
        return article_title

    if article_title:
        article_title_lower = article_title.lower()
        trend_has_signal = _contains_any_keyword(trend_title_lower, STYLE_INCLUDE_KEYWORDS)
        article_has_signal = _contains_any_keyword(article_title_lower, STYLE_INCLUDE_KEYWORDS)
        if (
            trend_title_lower in generic_titles
            or _looks_like_section_heading(trend_title)
            or (not trend_has_signal and article_has_signal)
        ):
            return article_title

    return trend_title


def _looks_like_section_heading(value: str) -> bool:
    title = str(value or "").strip().lower()
    if not title:
        return False
    if re.match(r"^\d+[\.\)]\s*", title):
        return True
    if "|" in title and ("then:" in title or "now:" in title):
        return True
    if title in {"meet the expert", "frequently asked questions", "related stories", "everything you need to know"}:
        return True
    if re.match(r"^(what|why|how|which|when|where)\b", title):
        return True
    return False


def _looks_like_hairstyle_only(*, title: str, summary: str, article_url: str) -> bool:
    title_text = title.lower()
    summary_text = summary.lower()
    url_text = article_url.lower()
    combined = f"{title_text} {summary_text} {url_text}"

    if _contains_any_keyword(combined, STYLE_EXCLUDE_KEYWORDS):
        return False

    has_title_signal = _contains_any_keyword(title_text, STYLE_INCLUDE_KEYWORDS)
    has_summary_signal = _contains_any_keyword(summary_text, STYLE_INCLUDE_KEYWORDS)
    has_url_signal = _contains_any_keyword(url_text, STYLE_URL_KEYWORDS)

    if has_title_signal or has_summary_signal or has_url_signal:
        return True

    return False


def _normalize_item(item: dict[str, Any]) -> dict[str, Any] | None:
    title = _pick_display_title(item)
    article_title = str(item.get("article_title") or "").strip()
    article_url = str(item.get("article_url") or "").strip()
    image_url = str(item.get("image_url") or "").strip()
    source = str(item.get("source") or "").strip() or "Unknown"
    description = item.get("summary") or item.get("description") or item.get("search_text") or ""
    published_at = str(item.get("published_at") or "").strip()
    crawled_at = str(item.get("crawled_at") or "").strip()
    category = str(item.get("category") or "").strip() or "trend"
    keywords = _extract_keywords(item)
    title_ko = str(item.get("title_ko") or "").strip()
    summary_ko = str(item.get("summary_ko") or "").strip()

    if not title:
        return None

    if not (
        _contains_any_keyword(title.lower(), STYLE_INCLUDE_KEYWORDS)
        or _contains_any_keyword(article_title.lower(), STYLE_INCLUDE_KEYWORDS)
    ):
        return None

    if not _looks_like_hairstyle_only(title=title, summary=str(description or ""), article_url=article_url):
        return None

    sort_at = _parse_datetime(published_at) or _parse_datetime(crawled_at)
    if sort_at is None:
        sort_at = datetime(1970, 1, 1, tzinfo=timezone.utc)

    if not published_at and _looks_like_listing_url(article_url):
        return None

    return {
        "title": title,
        "summary": _compact_summary(description),
        "image_url": image_url or None,
        "article_url": article_url or None,
        "source": source,
        "source_name": _display_source_name(source=source, article_url=article_url),
        "published_at": published_at or None,
        "crawled_at": crawled_at or None,
        "category": category,
        "keywords": keywords,
        "sort_at": sort_at,
        "has_published_at": bool(_parse_datetime(published_at)),
        "title_ko": title_ko,
        "summary_ko": summary_ko,
    }


def _translation_cache_key(item: dict[str, Any]) -> str:
    return str(item.get("article_url") or item.get("title") or "").strip()


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
        if isinstance(key, str) and isinstance(value, dict):
            cache[key] = {
                "title_ko": str(value.get("title_ko") or "").strip(),
                "summary_ko": str(value.get("summary_ko") or "").strip(),
            }
    return cache


def _save_translation_cache(cache: dict[str, dict[str, str]]) -> None:
    try:
        TRANSLATION_CACHE_FILE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        return


def _translate_missing_items(
    items: list[dict[str, Any]],
    cache: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    missing_items = [
        item
        for item in items
        if (not item.get("title_ko") or not item.get("summary_ko")) and _translation_cache_key(item) not in cache
    ]
    if not missing_items:
        return cache

    api_key = os.environ.get("GEMINI_API_KEY") or _get_django_setting("GEMINI_API_KEY", "")
    if not api_key:
        return cache

    try:
        from google import genai
    except Exception:
        return cache

    payload = [
        {
            "key": _translation_cache_key(item),
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
        }
        for item in missing_items
    ]
    prompt = (
        "Translate the following hairstyle trend article titles and summaries into natural Korean for a UI.\n"
        "Return only a JSON array.\n"
        'Each item must look like {"key":"...", "title_ko":"...", "summary_ko":"..."}.\n'
        "Keep brand names, people names, and publication names natural.\n"
        "Make titles concise and summaries readable.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=False)}"
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=(
                os.environ.get("TREND_TRANSLATION_MODEL")
                or _get_django_setting("TREND_TRANSLATION_MODEL", DEFAULT_TRANSLATION_MODEL)
            ),
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        translated_payload = json.loads(response.text)
    except Exception:
        return cache

    if not isinstance(translated_payload, list):
        return cache

    updated = dict(cache)
    for row in translated_payload:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        updated[key] = {
            "title_ko": str(row.get("title_ko") or "").strip(),
            "summary_ko": str(row.get("summary_ko") or "").strip(),
        }

    _save_translation_cache(updated)
    return updated


def _attach_korean_fields(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if all(item.get("title_ko") and item.get("summary_ko") for item in items):
        return items

    cache = _load_translation_cache()
    cache = _translate_missing_items(items, cache)

    localized_items: list[dict[str, Any]] = []
    for item in items:
        key = _translation_cache_key(item)
        translation = cache.get(key, {})
        localized_items.append(
            {
                **item,
                "title_ko": item.get("title_ko") or translation.get("title_ko") or item.get("title", ""),
                "summary_ko": item.get("summary_ko") or translation.get("summary_ko") or item.get("summary", ""),
            }
        )
    return localized_items


def get_latest_crawled_trends(*, limit: int = 5) -> dict[str, Any]:
    limit = max(1, min(int(limit), 5))
    cached_payload = _get_latest_trends_cached(limit)
    if cached_payload is not None:
        return cached_payload

    remote_payload = _load_runpod_latest_trends(limit=limit)
    if remote_payload is not None:
        return _set_latest_trends_cached(limit, remote_payload)

    source_label = "chromadb_trends"
    raw_items = _iter_chroma_items()
    if not raw_items:
        source_label = "refined_trends_json"
        raw_items = _load_json_list(REFINED_TRENDS_FILE)
    if not raw_items:
        source_label = "raw_trends_json"
        raw_items = _iter_raw_items()

    normalized_items: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for item in raw_items:
        normalized = _normalize_item(item)
        if normalized is None:
            continue
        dedupe_key = str(normalized.get("article_url") or normalized.get("title") or "")
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        normalized_items.append(normalized)

    normalized_items.sort(
        key=lambda item: (1 if item["has_published_at"] else 0, item["sort_at"]),
        reverse=True,
    )

    selected_items = [
        {
            "title": row["title"],
            "summary": row["summary"],
            "image_url": row["image_url"],
            "article_url": row["article_url"],
            "source": row["source"],
            "source_name": row.get("source_name") or row["source"],
            "published_at": row["published_at"],
            "crawled_at": row["crawled_at"],
            "category": row["category"],
            "keywords": row["keywords"],
            "title_ko": row.get("title_ko", ""),
            "summary_ko": row.get("summary_ko", ""),
        }
        for row in normalized_items[: max(1, min(int(limit), 5))]
    ]

    localized_items = _attach_korean_fields(selected_items)

    payload = {
        "status": "ready",
        "source": source_label,
        "count": len(localized_items),
        "items": localized_items,
    }
    return _set_latest_trends_cached(limit, payload)
