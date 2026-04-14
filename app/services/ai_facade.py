import base64
import json
import logging
import os
import time
from math import dist
from types import SimpleNamespace

import requests

from app.api.v1.recommendation_logic import (
    DEFAULT_SCORING_WEIGHTS,
    ScoringWeights,
    canonical_budget,
    canonical_gender_branch,
    canonical_length,
    canonical_scalp,
    canonical_vibe,
    score_recommendations,
)


logger = logging.getLogger(__name__)


_AI_HEALTH_CACHE: dict[str, object] = {
    "expires_at": 0.0,
    "payload": None,
}


def _service_base_url() -> str:
    base = _runpod_base_url()
    endpoint = _runpod_endpoint_id()
    if base and endpoint:
        return f"{base}/{endpoint}"
    return ""


def _internal_api_token() -> str:
    return _runpod_api_key()


def _legacy_internal_api_key() -> str:
    return os.environ.get("MIRRAI_INTERNAL_API_KEY", "").strip()


def _service_api_version() -> str:
    return os.environ.get("MIRRAI_AI_API_VERSION", "").strip()


def _runpod_base_url() -> str:
    return os.environ.get("RUNPOD_BASE_URL", "https://api.runpod.ai/v2").rstrip("/")


def _runpod_api_key() -> str:
    return os.environ.get("RUNPOD_API_KEY", "").strip()


def _runpod_endpoint_id() -> str:
    return os.environ.get("RUNPOD_ENDPOINT_ID", "").strip()


def _runpod_health_timeout() -> tuple[int, int]:
    read_timeout = int(os.environ.get("MIRRAI_AI_HEALTH_TIMEOUT", "5"))
    return (3, max(3, read_timeout))


def _service_timeout() -> int:
    return max(3, int(os.environ.get("MIRRAI_AI_SERVICE_TIMEOUT", "5")))


def _health_cache_seconds() -> int:
    return max(0, int(os.environ.get("MIRRAI_AI_HEALTH_CACHE_SECONDS", "15")))


def _health_cache_key() -> str:
    prefix = str(os.environ.get("REDIS_KEY_PREFIX", "mirrai")).strip() or "mirrai"
    return f"{prefix}:cache:ai-health:v1:{_ai_provider()}"


def _get_cached_health_payload() -> dict | None:
    try:
        from app.services.runtime_cache import get_cached_payload

        payload = get_cached_payload(_health_cache_key())
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _set_cached_health_payload(payload: dict, timeout: int) -> None:
    try:
        from app.services.runtime_cache import set_cached_payload

        set_cached_payload(_health_cache_key(), payload, timeout=timeout)
    except Exception:
        return


def _runpod_enabled() -> bool:
    return bool(_runpod_api_key() and _runpod_endpoint_id())


def _service_enabled() -> bool:
    return bool(_service_base_url())


def _ai_provider() -> str:
    configured = os.environ.get("MIRRAI_AI_PROVIDER", "").strip().lower()
    if configured == "runpod":
        if _runpod_enabled():
            return "runpod"
        if _service_enabled():
            return "service"
        return "local"
    if configured == "service":
        if _service_enabled():
            return "service"
        if _runpod_enabled():
            return "runpod"
        return "local"
    if configured == "local":
        return "local"
    if _runpod_enabled():
        return "runpod"
    if _service_enabled():
        return "service"
    return "local"


def get_ai_runtime_config_snapshot() -> dict:
    configured_provider = os.environ.get("MIRRAI_AI_PROVIDER", "").strip().lower() or "auto"
    endpoint_id = _runpod_endpoint_id()
    service_url = _service_base_url()
    return {
        "configured_provider": configured_provider,
        "resolved_provider": _ai_provider(),
        "service_enabled": _service_enabled(),
        "service_url_configured": bool(service_url),
        "service_api_version": (_service_api_version() or None),
        "service_token_configured": bool(_internal_api_token() or _legacy_internal_api_key()),
        "runpod_enabled": _runpod_enabled(),
        "runpod_api_key_configured": bool(_runpod_api_key()),
        "runpod_endpoint_id_configured": bool(endpoint_id),
    }


def _extract_runpod_output(payload: dict) -> dict | None:
    if not isinstance(payload, dict):
        return {"output": payload} if payload is not None else None
    output = payload.get("output")
    if isinstance(output, dict):
        return output
    if output is not None:
        return {
            "output": output,
            "status": payload.get("status"),
            "id": payload.get("id"),
            "delayTime": payload.get("delayTime"),
            "executionTime": payload.get("executionTime"),
        }
    if any(key in payload for key in ("results", "recommendations", "cuda", "status")):
        return payload
    return None


def _runpod_poll_interval_seconds() -> float:
    return max(0.2, float(os.environ.get("RUNPOD_POLL_INTERVAL_SECONDS", "1.0")))


def _fetch_runpod_output_url(output_url: str, *, timeout_seconds: int) -> dict | None:
    response = requests.get(output_url, timeout=min(max(timeout_seconds, 3), 120))
    response.raise_for_status()
    return _extract_runpod_output(response.json())


def _poll_runpod_job_until_complete(*, job_id: str, timeout_seconds: int) -> dict | None:
    deadline = time.monotonic() + max(3, timeout_seconds)
    status_url = f"{_runpod_base_url()}/{_runpod_endpoint_id()}/status/{job_id}"
    headers = {"Authorization": f"Bearer {_runpod_api_key()}"}

    while time.monotonic() < deadline:
        response = requests.get(status_url, headers=headers, timeout=min(max(timeout_seconds, 3), 60))
        response.raise_for_status()
        payload = response.json()
        status = str((payload or {}).get("status") or "").upper()

        if status == "COMPLETED":
            output_url = str((payload or {}).get("output_url") or "").strip()
            if output_url:
                return _fetch_runpod_output_url(output_url, timeout_seconds=timeout_seconds)
            return _extract_runpod_output(payload)
        if status in {"FAILED", "CANCELLED", "TIMED_OUT"}:
            logger.warning(
                "[runpod_poll_failed] job_id=%s status=%s keys=%s error=%s",
                job_id,
                status,
                sorted(payload.keys()) if isinstance(payload, dict) else None,
                (payload or {}).get("error") if isinstance(payload, dict) else None,
            )
            return _extract_runpod_output(payload)

        time.sleep(_runpod_poll_interval_seconds())

    logger.warning("[runpod_poll_timeout] job_id=%s timeout_seconds=%s", job_id, timeout_seconds)
    return None


def _resolve_runpod_sync_payload(payload: dict, *, timeout_seconds: int) -> dict | None:
    if not isinstance(payload, dict):
        return _extract_runpod_output(payload)

    status = str(payload.get("status") or "").upper()
    job_id = str(payload.get("id") or "").strip()
    output_url = str(payload.get("output_url") or "").strip()

    if status in {"IN_QUEUE", "IN_PROGRESS"} and job_id:
        return _poll_runpod_job_until_complete(job_id=job_id, timeout_seconds=timeout_seconds)
    if status == "COMPLETED" and output_url:
        return _fetch_runpod_output_url(output_url, timeout_seconds=timeout_seconds)
    return _extract_runpod_output(payload)


def _post_runpod(input_payload: dict, *, sync: bool = True, timeout: tuple[int, int] | None = None) -> dict | None:
    if not _runpod_enabled():
        return None

    route = "runsync" if sync else "run"
    url = f"{_runpod_base_url()}/{_runpod_endpoint_id()}/{route}"
    try:
        response = requests.post(
            url,
            json={"input": input_payload},
            headers={
                "Authorization": f"Bearer {_runpod_api_key()}",
                "Content-Type": "application/json",
            },
            timeout=timeout or (5, 120),
        )
        response.raise_for_status()
        payload = response.json()
        timeout_seconds = int((timeout or (5, 120))[1])
        resolved = _resolve_runpod_sync_payload(payload, timeout_seconds=timeout_seconds) if sync else _extract_runpod_output(payload)
        if resolved is None:
            logger.warning(
                "[runpod_response_unrecognized] route=%s status=%s keys=%s",
                route,
                (payload or {}).get("status") if isinstance(payload, dict) else None,
                sorted(payload.keys()) if isinstance(payload, dict) else None,
            )
        return resolved
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Falling back after RunPod call failure: %s", exc)
        return None


def _service_headers(*, include_json_content_type: bool) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
    }
    token = _internal_api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    legacy_api_key = _legacy_internal_api_key()
    if legacy_api_key:
        headers["X-Internal-API-Key"] = legacy_api_key
    api_version = _service_api_version()
    if api_version:
        headers["X-MirrAI-API-Version"] = api_version
    if include_json_content_type:
        headers["Content-Type"] = "application/json"
    return headers


def _request_service(method: str, path: str, payload: dict | None = None) -> dict | None:
    base_url = _service_base_url()
    if not base_url:
        return None

    try:
        response = requests.request(
            method=method.upper(),
            url=f"{base_url}{path}",
            json=payload if payload is not None else None,
            headers=_service_headers(include_json_content_type=payload is not None),
            timeout=(3, _service_timeout()),
        )
        try:
            parsed = response.json()
        except ValueError:
            parsed = None

        if response.ok:
            if isinstance(parsed, dict):
                return parsed
            logger.warning(
                "AI service returned a non-JSON success response. method=%s path=%s status=%s",
                method.upper(),
                path,
                response.status_code,
            )
            return None

        error_code = None
        retryable = None
        message = response.text[:200]
        if isinstance(parsed, dict):
            error_obj = parsed.get("error") or {}
            error_code = error_obj.get("error_code") or parsed.get("error_code")
            retryable = error_obj.get("retryable") if "retryable" in error_obj else parsed.get("retryable")
            message = error_obj.get("message") or parsed.get("message") or parsed.get("detail") or message
        logger.warning(
            "AI service request failed. method=%s path=%s status=%s error_code=%s retryable=%s message=%s",
            method.upper(),
            path,
            response.status_code,
            error_code,
            retryable,
            message,
        )
        return None
    except requests.RequestException as exc:
        logger.warning("Falling back to local AI facade after remote call failure: %s", exc)
        return None


def _response_meta(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    return {
        "schema_version": payload.get("schema_version"),
        "response_version": payload.get("response_version"),
        "request_id": payload.get("request_id"),
        "processing_time_ms": payload.get("processing_time_ms"),
    }


def _with_response_meta(data: dict, payload: dict | None) -> dict:
    metadata = {key: value for key, value in _response_meta(payload).items() if value is not None}
    if metadata:
        data.setdefault("response_meta", metadata)
    return data


def _unwrap_service_data(payload: dict | None, *, allow_partial_success: bool = False) -> dict | None:
    if not isinstance(payload, dict):
        return None

    status = str(payload.get("status") or "").lower()
    data = payload.get("data")
    if isinstance(data, dict):
        if status in {"ok", "success"} or (allow_partial_success and status == "partial_success"):
            normalized = dict(data)
            partial_failures = payload.get("partial_failures")
            if allow_partial_success and status == "partial_success" and isinstance(partial_failures, list):
                normalized["partial_failures"] = list(partial_failures)
            normalized["service_status"] = status
            return _with_response_meta(normalized, payload)
        if status == "error":
            error_obj = payload.get("error") or {}
            logger.warning(
                "AI service returned an error payload. error_code=%s message=%s retryable=%s",
                error_obj.get("error_code") or payload.get("error_code"),
                error_obj.get("message") or payload.get("message"),
                error_obj.get("retryable") if "retryable" in error_obj else payload.get("retryable"),
            )
            return None
    return payload


def _normalize_health_payload(payload: dict | None) -> dict | None:
    data = _unwrap_service_data(payload) or payload
    if not isinstance(data, dict):
        return None

    raw_status = str((payload or {}).get("status") or data.get("status") or "success").lower()
    if raw_status in {"success", "ok", "ready"}:
        status = "online"
    elif raw_status == "partial_success":
        status = "degraded"
    elif raw_status in {"reachable", "warning"}:
        status = "reachable"
    elif raw_status in {"offline", "error"}:
        status = "offline"
    else:
        status = raw_status

    return {
        "status": status,
        "mode": "service",
        "message": data.get("role") or data.get("message") or "ai-microservice",
        "service_role": data.get("role"),
        "build_version": data.get("build_version"),
        "model_version": data.get("model_version"),
        "uptime_seconds": data.get("uptime_seconds"),
        "service_status": data.get("service_status") or raw_status,
        **_response_meta(payload),
    }


def _normalize_analysis_payload(payload: dict | None, *, fallback_image_url: str | None) -> dict | None:
    data = _unwrap_service_data(payload) or payload
    if not isinstance(data, dict):
        return None
    if data.get("face_shape") is None or data.get("golden_ratio_score") is None:
        return None

    normalized = dict(data)
    visualization = normalized.get("visualization")
    if isinstance(visualization, dict) and visualization.get("image_url") and not normalized.get("image_url"):
        normalized["image_url"] = visualization["image_url"]
    normalized.setdefault("image_url", fallback_image_url)
    return _with_response_meta(normalized, payload)


def _normalize_simulation_items(payload: dict | None) -> list[dict] | None:
    data = _unwrap_service_data(payload, allow_partial_success=True)
    if not isinstance(data, dict):
        return None

    items = data.get("items")
    if not isinstance(items, list):
        return None

    partial_failures = data.get("partial_failures")
    normalized_items: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        if normalized.get("match_score") is None and normalized.get("score") is not None:
            normalized["match_score"] = normalized.get("score")
        simulation_image_url = normalized.get("simulation_image_url")
        if simulation_image_url and not normalized.get("synthetic_image_url"):
            normalized["synthetic_image_url"] = simulation_image_url
        reasoning_snapshot = dict(normalized.get("reasoning_snapshot") or {})
        reasoning_snapshot.setdefault("service_status", data.get("service_status"))
        if isinstance(partial_failures, list) and partial_failures:
            reasoning_snapshot.setdefault("partial_failures", partial_failures)
        if normalized.get("llm_explanation") and not normalized.get("reasoning"):
            normalized["reasoning"] = normalized["llm_explanation"]
        normalized["reasoning_snapshot"] = reasoning_snapshot
        normalized_items.append(_with_response_meta(normalized, payload))
    return normalized_items


def _normalize_explain_style_payload(payload: dict | None, *, card: dict) -> dict | None:
    data = _unwrap_service_data(payload) or payload
    if not isinstance(data, dict):
        return None

    returned_card = data.get("card")
    normalized = dict(card)
    if isinstance(returned_card, dict):
        normalized.update(returned_card)
    for key in ("style_id", "style_name", "sample_image_url", "simulation_image_url", "llm_explanation", "keywords"):
        if data.get(key) is not None:
            normalized[key] = data.get(key)
    return _with_response_meta(normalized, payload)


def _compute_ai_health() -> dict:
    provider = _ai_provider()
    if provider == "runpod":
        payload = _post_runpod({"action": "health_check"}, timeout=_runpod_health_timeout())
        if payload:
            raw_status = str(payload.get("status", "ok")).lower()
            if raw_status in {"ok", "completed"}:
                status = "online"
            elif raw_status in {"failed", "error"}:
                status = "reachable"
            else:
                status = raw_status
            result = {
                "status": status,
                "mode": "runpod",
                "message": (
                    payload.get("cuda", {}).get("device")
                    or payload.get("error")
                    or payload.get("message")
                    or "runpod"
                ),
            }
            logger.info("[ai_health] provider=runpod status=%s message=%s", result["status"], result["message"])
            return result
        result = {
            "status": "offline",
            "mode": "runpod",
            "message": "RunPod health check failed.",
        }
        logger.info("[ai_health] provider=runpod status=%s message=%s", result["status"], result["message"])
        return result

    if provider == "service":
        remote = _request_service("GET", "/internal/health")
        normalized = _normalize_health_payload(remote)
        if normalized:
            logger.info("[ai_health] provider=service status=%s message=%s", normalized.get("status"), normalized.get("message"))
            return normalized
        result = {
            "status": "offline",
            "mode": "service",
            "message": "Configured AI service is unavailable.",
        }
        logger.info("[ai_health] provider=service status=%s message=%s", result["status"], result["message"])
        return result

    result = {
        "status": "fallback",
        "mode": "local",
        "message": "Local AI fallback is active.",
    }
    logger.info("[ai_health] provider=local status=%s message=%s", result["status"], result["message"])
    return result


def build_ai_runtime_diagnostic_snapshot(*, use_cache: bool = True) -> dict:
    config = get_ai_runtime_config_snapshot()
    health = get_ai_health(use_cache=use_cache)
    warnings: list[str] = []

    configured_provider = config.get("configured_provider")
    resolved_provider = config.get("resolved_provider")
    health_mode = health.get("mode")

    if configured_provider == "service" and not config.get("service_url_configured"):
        warnings.append("configured_service_but_url_missing")
    if configured_provider == "service" and not config.get("service_token_configured"):
        warnings.append("configured_service_but_token_missing")
    if configured_provider == "runpod" and not config.get("runpod_api_key_configured"):
        warnings.append("configured_runpod_but_api_key_missing")
    if configured_provider == "runpod" and not config.get("runpod_endpoint_id_configured"):
        warnings.append("configured_runpod_but_endpoint_missing")
    if resolved_provider == "service" and health_mode == "local":
        warnings.append("service_resolved_but_local_fallback_active")
    if resolved_provider == "runpod" and health_mode == "local":
        warnings.append("runpod_resolved_but_local_fallback_active")
    if health_mode == "service" and health.get("status") == "offline":
        warnings.append("service_health_offline")
    if health_mode == "runpod" and health.get("status") == "offline":
        warnings.append("runpod_health_offline")

    return {
        "config": config,
        "health": health,
        "warnings": warnings,
    }


def _face_analysis_runtime_mode(config: dict) -> str:
    if config.get("service_enabled"):
        return "service_remote"
    return "local_mock_fallback"


def _recommendation_runtime_mode(config: dict) -> str:
    resolved_provider = config.get("resolved_provider")
    if resolved_provider == "service":
        return "service_remote"
    if resolved_provider == "runpod":
        return "local_scoring_with_runpod_augmentation"
    return "local_scoring_fallback"


def build_model_connection_validation_snapshot(*, attempts: int = 3, use_cache: bool = False) -> dict:
    config = get_ai_runtime_config_snapshot()
    attempts = max(1, int(attempts or 1))

    probes: list[dict] = []
    status_counts: dict[str, int] = {}
    mode_counts: dict[str, int] = {}
    online_count = 0
    offline_count = 0

    for index in range(attempts):
        started_at = time.monotonic()
        health = get_ai_health(use_cache=(use_cache and index == 0))
        elapsed_ms = int((time.monotonic() - started_at) * 1000)

        status = str(health.get("status") or "unknown")
        mode = str(health.get("mode") or "unknown")
        if status == "online":
            online_count += 1
        if status == "offline":
            offline_count += 1

        status_counts[status] = status_counts.get(status, 0) + 1
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        probes.append(
            {
                "attempt": index + 1,
                "mode": mode,
                "status": status,
                "message": health.get("message"),
                "cached": bool(health.get("cached")),
                "elapsed_ms": elapsed_ms,
            }
        )

    overall_state = "healthy"
    if online_count == 0 and offline_count == attempts:
        overall_state = "offline"
    elif online_count == 0:
        overall_state = "fallback_only"
    elif offline_count > 0:
        overall_state = "unstable"

    warnings: list[str] = []
    if config.get("resolved_provider") == "runpod" and not config.get("service_enabled"):
        warnings.append("face_analysis_uses_local_mock_fallback")
    if config.get("resolved_provider") == "runpod" and online_count and offline_count:
        warnings.append("runpod_health_flaky")
    if config.get("resolved_provider") == "runpod" and online_count == 0:
        warnings.append("runpod_health_unavailable")
    if config.get("resolved_provider") == "local":
        warnings.append("remote_model_not_active")

    return {
        "config": config,
        "summary": {
            "attempts": attempts,
            "overall_state": overall_state,
            "online_count": online_count,
            "offline_count": offline_count,
            "status_counts": status_counts,
            "mode_counts": mode_counts,
            "face_analysis_mode": _face_analysis_runtime_mode(config),
            "recommendation_mode": _recommendation_runtime_mode(config),
        },
        "probes": probes,
        "warnings": warnings,
    }


def get_ai_health(*, use_cache: bool = True) -> dict:
    cache_seconds = _health_cache_seconds()
    now = time.monotonic()

    if use_cache and cache_seconds > 0:
        redis_payload = _get_cached_health_payload()
        if isinstance(redis_payload, dict):
            payload = dict(redis_payload)
            payload["cached"] = True
            return payload

    cached_payload = _AI_HEALTH_CACHE.get("payload")
    expires_at = float(_AI_HEALTH_CACHE.get("expires_at") or 0.0)

    if use_cache and cache_seconds > 0 and isinstance(cached_payload, dict) and now < expires_at:
        payload = dict(cached_payload)
        payload["cached"] = True
        return payload

    payload = _compute_ai_health()
    payload["cached"] = False
    if cache_seconds > 0:
        _set_cached_health_payload(payload, cache_seconds)
        _AI_HEALTH_CACHE["payload"] = dict(payload)
        _AI_HEALTH_CACHE["expires_at"] = now + cache_seconds
    return payload


def _build_preference_payload(survey_data: dict | None) -> dict:
    survey_data = survey_data or {}
    length = canonical_length(survey_data.get("target_length"))
    mood = canonical_vibe(survey_data.get("target_vibe"))
    hair_type = canonical_scalp(survey_data.get("scalp_type"))
    budget = canonical_budget(survey_data.get("budget_range"))

    payload: dict[str, object] = {}
    if length != "unknown":
        payload["length"] = "medium" if length == "bob" else length
    if mood != "unknown":
        payload["mood"] = [mood]
    if hair_type in {"straight", "waved", "curly"}:
        payload["hair_type"] = {"waved": "wavy"}.get(hair_type, hair_type)
    if budget != "unknown":
        payload["budget"] = {"mid": "medium"}.get(budget, budget)
    return payload


def _survey_profile_dict(survey_data: dict | None) -> dict:
    survey_data = survey_data or {}
    value = survey_data.get("survey_profile")
    return value if isinstance(value, dict) else {}


def _survey_gender_branch(survey_data: dict | None) -> str:
    survey_profile = _survey_profile_dict(survey_data)
    return canonical_gender_branch(survey_profile.get("gender_branch"))


def _survey_style_axes(survey_data: dict | None) -> dict:
    survey_profile = _survey_profile_dict(survey_data)
    value = survey_profile.get("style_axes")
    return value if isinstance(value, dict) else {}


def _unique_prompt_parts(parts: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for part in parts:
        text = str(part or "").strip()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _build_male_hairstyle_text(survey_data: dict | None) -> str:
    survey_data = survey_data or {}
    style_axes = _survey_style_axes(survey_data)
    length = canonical_length(survey_data.get("target_length"))
    mood = canonical_vibe(survey_data.get("target_vibe"))
    hair_type = canonical_scalp(survey_data.get("scalp_type"))

    parts = ["male haircut", "masculine salon style"]
    length_phrase = {
        "short": "short crop",
        "medium": "medium two-block",
        "long": "medium flow",
        "bob": "short crop",
    }.get(length)
    if length_phrase:
        parts.append(length_phrase)

    two_block = str(style_axes.get("two_block") or "").strip()
    if two_block == "strong":
        parts.append("defined two-block")
    elif two_block == "soft":
        parts.append("soft two-block")
    elif two_block == "none":
        parts.append("connected side line")

    front_styling = str(style_axes.get("front_styling") or "").strip()
    if front_styling == "up":
        parts.append("up styling")
    elif front_styling == "down":
        parts.append("down styling")
    elif front_styling == "flexible":
        parts.append("flexible front styling")

    parting = str(style_axes.get("parting") or "").strip()
    if parting == "parted":
        parts.append("parted fringe")
    elif parting == "non_parted":
        parts.append("non-parted fringe")
    elif parting == "either":
        parts.append("natural parting")

    if hair_type == "straight":
        parts.append("clean straight texture")
    elif hair_type == "waved":
        parts.append("soft volume")
    elif hair_type == "curly":
        parts.append("curly texture")

    mood_phrase = {
        "natural": "natural mood",
        "chic": "clean chic mood",
        "elegant": "refined mood",
        "cute": "soft youthful mood",
    }.get(mood)
    if mood_phrase:
        parts.append(mood_phrase)

    return ", ".join(_unique_prompt_parts(parts)) or "male haircut"


def _build_female_hairstyle_text(survey_data: dict | None) -> str:
    survey_data = survey_data or {}
    style_axes = _survey_style_axes(survey_data)
    parts = [
        str(survey_data.get("target_length") or "").strip(),
        str(survey_data.get("target_vibe") or "").strip(),
    ]

    silhouette = str(style_axes.get("silhouette") or "").strip()
    if silhouette == "layered":
        parts.append("layered silhouette")
    elif silhouette == "voluminous":
        parts.append("volume silhouette")
    elif silhouette == "straight_line":
        parts.append("clean line silhouette")

    bang_preference = str(style_axes.get("bang_preference") or "").strip()
    if bang_preference == "no_bangs":
        parts.append("no bangs")
    elif bang_preference == "light_bangs":
        parts.append("light bangs")
    elif bang_preference == "statement_bangs":
        parts.append("statement bangs")

    return " ".join(part for part in _unique_prompt_parts(parts) if part) or "natural"


def _build_runpod_preference_payload(survey_data: dict | None) -> dict:
    survey_data = survey_data or {}
    length = canonical_length(survey_data.get("target_length"))
    mood = canonical_vibe(survey_data.get("target_vibe"))
    hair_type = canonical_scalp(survey_data.get("scalp_type"))
    budget = canonical_budget(survey_data.get("budget_range"))

    mood_mapping = {
        "natural": "natural",
        "chic": "trendy",
        "cute": "cute",
        "elegant": "classic",
    }

    payload: dict[str, object] = {}
    if length != "unknown":
        payload["length"] = "medium" if length == "bob" else length
    mapped_mood = mood_mapping.get(mood)
    if mapped_mood:
        payload["mood"] = [mapped_mood]
    if hair_type in {"straight", "waved", "curly"}:
        payload["hair_type"] = {"waved": "wavy"}.get(hair_type, hair_type)
    if budget != "unknown":
        payload["budget"] = {"mid": "medium"}.get(budget, budget)
    gender_branch = _survey_gender_branch(survey_data)
    if gender_branch:
        payload["gender_branch"] = gender_branch
    return payload


def _build_preference_text(survey_data: dict | None) -> str | None:
    survey_data = survey_data or {}
    gender_branch = _survey_gender_branch(survey_data)
    style_axes = _survey_style_axes(survey_data)

    if gender_branch == "male":
        parts = [
            "gender=male",
            f"length={canonical_length(survey_data.get('target_length'))}",
            f"mood={canonical_vibe(survey_data.get('target_vibe'))}",
            f"texture={canonical_scalp(survey_data.get('scalp_type'))}",
            f"color={str(survey_data.get('hair_colour') or '').strip()}",
            f"budget={canonical_budget(survey_data.get('budget_range'))}",
            f"two_block={style_axes.get('two_block') or 'soft'}",
            f"front={style_axes.get('front_styling') or 'flexible'}",
            f"parting={style_axes.get('parting') or 'either'}",
            "male salon vocabulary only",
        ]
    else:
        parts = [
            str(survey_data.get("target_length") or "").strip(),
            str(survey_data.get("target_vibe") or "").strip(),
            str(survey_data.get("scalp_type") or "").strip(),
            str(survey_data.get("hair_colour") or "").strip(),
            str(survey_data.get("budget_range") or "").strip(),
        ]
    text = ", ".join(part for part in parts if part)
    return text or None


def _build_hairstyle_text(survey_data: dict | None) -> str:
    if _survey_gender_branch(survey_data) == "male":
        return _build_male_hairstyle_text(survey_data)
    return _build_female_hairstyle_text(survey_data)


def build_recommendation_debug_payload(
    *,
    survey_data: dict | None,
    analysis_data: dict | None,
    scoring_weights: ScoringWeights | None = None,
    recommendation_stage: str | None = None,
) -> dict:
    survey_data = survey_data or {}
    analysis_data = analysis_data or {}
    scoring_weights = scoring_weights or DEFAULT_SCORING_WEIGHTS

    color_text = str(survey_data.get("hair_colour") or "").strip() or None
    preference_payload = _build_runpod_preference_payload(survey_data)
    preference_text = _build_preference_text(survey_data)
    resolved_stage = str(recommendation_stage or "initial").strip() or "initial"
    runtime_snapshot = get_ai_runtime_config_snapshot()

    return {
        "recommendation_stage": resolved_stage,
        "ai_runtime": {
            "configured_provider": runtime_snapshot.get("configured_provider"),
            "resolved_provider": runtime_snapshot.get("resolved_provider"),
        },
        "survey_data": {
            "target_length": survey_data.get("target_length"),
            "target_vibe": survey_data.get("target_vibe"),
            "scalp_type": survey_data.get("scalp_type"),
            "hair_colour": survey_data.get("hair_colour"),
            "budget_range": survey_data.get("budget_range"),
            "question_answers": dict(survey_data.get("question_answers") or {}),
            "survey_profile": dict(survey_data.get("survey_profile") or {}),
        },
        "analysis_summary": {
            "face_shape": analysis_data.get("face_shape"),
            "golden_ratio_score": analysis_data.get("golden_ratio_score"),
        },
        "runpod_payload": {
            "hairstyle_text": _build_hairstyle_text(survey_data),
            "color_text": color_text,
            "top_k": 5,
            "return_base64": True,
        },
        "direct_runpod_payload": {
            "preference": preference_payload or None,
            "preference_text": preference_text,
        },
        "match_score_basis": {
            "formula": "face_score + ratio_score + preference_score - penalty",
            "weights": scoring_weights.as_dict(),
            "description": (
                "카드의 xx% 매칭은 얼굴형 적합도, 얼굴 비율 점수, 취향 일치도를 더하고 "
                "불일치 패널티를 뺀 로컬 점수입니다."
            ),
        },
    }


def _build_runpod_image_payload(analysis_data: dict) -> dict | None:
    image_base64 = str(analysis_data.get("image_base64") or "").strip()
    if image_base64:
        return {"image_base64": image_base64}

    image_url = str(analysis_data.get("image_url") or "").strip()
    if image_url.startswith(("http://", "https://")):
        return {"image_url": image_url}

    return None


def _build_face_ratios(analysis_data: dict | None) -> dict | None:
    analysis_data = analysis_data or {}
    snapshot = analysis_data.get("landmark_snapshot") or {}
    face_bbox = snapshot.get("face_bbox") or {}
    landmarks = snapshot.get("landmarks") or {}
    if not face_bbox:
        logger.warning(
            "[face_ratios_failed] reason=no_face_bbox snapshot_keys=%s",
            sorted(snapshot.keys()),
        )
        return None

    face_height = float(face_bbox.get("height") or 0)
    face_width = float(face_bbox.get("width") or 0)
    if face_height <= 0 or face_width <= 0:
        logger.warning(
            "[face_ratios_failed] reason=zero_face_dimensions face_width=%s face_height=%s",
            face_width,
            face_height,
        )
        return None

    left_eye = (landmarks.get("left_eye") or {}).get("point")
    right_eye = (landmarks.get("right_eye") or {}).get("point")
    mouth_center = (landmarks.get("mouth_center") or {}).get("point")
    chin_center = (landmarks.get("chin_center") or {}).get("point")
    if not (left_eye and right_eye and mouth_center and chin_center):
        logger.warning(
            "[face_ratios_failed] reason=missing_landmarks has_left_eye=%s has_right_eye=%s has_mouth=%s has_chin=%s landmark_keys=%s",
            bool(left_eye),
            bool(right_eye),
            bool(mouth_center),
            bool(chin_center),
            sorted(landmarks.keys()),
        )
        return None

    eye_distance = dist((left_eye["x"], left_eye["y"]), (right_eye["x"], right_eye["y"]))
    jaw_height = max(0.0, float(chin_center["y"]) - float(mouth_center["y"]))
    if eye_distance <= 0 or jaw_height <= 0:
        return None

    return {
        "cheekbone_to_height": round(eye_distance / face_height, 4),
        "jaw_to_height": round(jaw_height / face_height, 4),
        "temple_to_height": round(face_width / face_height, 4),
        "jaw_to_cheekbone": round(face_width / eye_distance, 4),
    }


def _match_runpod_recommendation(
    *,
    recommendations: list[dict],
    index: int,
    result: dict,
) -> dict | None:
    if index < len(recommendations) and isinstance(recommendations[index], dict):
        return recommendations[index]

    recommended_style = result.get("recommended_style") or {}
    recommended_style_id = str(recommended_style.get("style_id") or "").strip()
    recommended_style_name = str(recommended_style.get("style_name") or "").strip().lower()
    if not recommended_style_id and not recommended_style_name:
        return None

    for recommendation in recommendations:
        if not isinstance(recommendation, dict):
            continue
        candidate_id = str(recommendation.get("style_id") or "").strip()
        candidate_name = str(recommendation.get("style_name") or "").strip().lower()
        if recommended_style_id and candidate_id and candidate_id == recommended_style_id:
            return recommendation
        if recommended_style_name and candidate_name and candidate_name == recommended_style_name:
            return recommendation
    return None


def _rag_context_excerpt(value: object, *, limit: int = 280) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _normalize_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _build_runpod_recommendation_payload(
    items: list[dict],
    *,
    analysis_data: dict | None = None,
) -> list[dict]:
    analysis_data = analysis_data or {}
    payload: list[dict] = []
    for index, item in enumerate(items[:5], start=1):
        style_name = str(item.get("style_name") or "").strip()
        if not style_name:
            continue

        reasoning_snapshot = dict(item.get("reasoning_snapshot") or {})
        payload.append(
            {
                "rank": int(item.get("rank") or index),
                "style_id": item.get("style_id"),
                "style_name": style_name,
                "hairstyle_text": str(item.get("hairstyle_text") or style_name).strip(),
                "description": str(
                    item.get("style_description")
                    or item.get("llm_explanation")
                    or reasoning_snapshot.get("summary")
                    or ""
                ).strip(),
                "score": item.get("match_score") if item.get("match_score") is not None else item.get("score"),
                "face_shapes": _normalize_list(
                    item.get("face_shapes")
                    or reasoning_snapshot.get("matched_face_shapes")
                    or reasoning_snapshot.get("face_shapes")
                ),
                "face_shape_detected": analysis_data.get("face_shape") or reasoning_snapshot.get("face_shape"),
                "golden_ratio_score": analysis_data.get("golden_ratio_score") or item.get("golden_ratio_score"),
            }
        )
    return payload


def _fetch_rag_context_for_items(items: list[dict]) -> str | None:
    try:
        from app.trend_pipeline.rag_query import build_context, retrieve
    except Exception as exc:
        logger.warning("Local trend RAG query module is unavailable: %s", exc)
        return None

    documents: list[dict] = []
    seen_titles: set[str] = set()
    for item in items[:3]:
        style_name = str(item.get("style_name") or item.get("hairstyle_text") or "").strip()
        if not style_name:
            continue
        try:
            for doc in retrieve(style_name, n_results=3, expand=True):
                title = str(doc.get("title") or "").strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                documents.append(doc)
        except Exception as exc:
            logger.warning("Local trend RAG lookup failed for style '%s': %s", style_name, exc)

    if not documents:
        return None
    return build_context(documents[:5])


def _augment_items_with_runpod(
    *,
    items: list[dict],
    survey_data: dict | None,
    analysis_data: dict,
) -> list[dict]:
    if _ai_provider() != "runpod":
        return items

    image_payload = _build_runpod_image_payload(analysis_data)
    if not image_payload:
        return items

    hairstyle_text = _build_hairstyle_text(survey_data)
    color_text = str((survey_data or {}).get("hair_colour") or "").strip()
    preference = _build_runpod_preference_payload(survey_data)
    preference_text = _build_preference_text(survey_data)

    runpod_payload = {
        **image_payload,
        "hairstyle_text": hairstyle_text,
        "top_k": min(len(items), 5),
        "return_base64": True,
    }
    if color_text:
        runpod_payload["color_text"] = color_text
    if preference:
        runpod_payload["preference"] = preference
    if preference_text:
        runpod_payload["preference_text"] = preference_text

    logger.info(
        "[runpod_augment] hairstyle_text=%s color_text=%s preference_text=%s top_k=%s",
        hairstyle_text,
        color_text or None,
        preference_text,
        runpod_payload["top_k"],
    )

    remote = _post_runpod(runpod_payload)
    if not remote:
        return items

    results = remote.get("results")
    if not isinstance(results, list) or not results:
        logger.warning("[runpod_augment] no results in response. remote_keys=%s", sorted(remote.keys()))
        return items

    build_tag = str(remote.get("build_tag") or "").strip() or None
    runpod_runtime = remote.get("runpod") if isinstance(remote.get("runpod"), dict) else {}

    augmented: list[dict] = []
    for index, item in enumerate(items):
        enriched = dict(item)
        if index < len(results):
            result = results[index] or {}
            image_base64 = result.get("image_base64")
            if image_base64:
                data_url = f"data:image/png;base64,{image_base64}"
                enriched["simulation_image_url"] = data_url
                enriched["synthetic_image_url"] = data_url
            snapshot = dict(enriched.get("reasoning_snapshot") or {})
            snapshot["runpod"] = {
                "provider": "runpod",
                "clip_score": result.get("clip_score"),
                "mask_used": result.get("mask_used"),
                "elapsed_seconds": remote.get("elapsed_seconds"),
                "build_tag": build_tag,
                "runtime": runpod_runtime,
            }
            enriched["reasoning_snapshot"] = snapshot
        augmented.append(enriched)

    logger.info(
        "[runpod_augment] done. items=%s simulated=%s",
        len(augmented),
        sum(1 for item in augmented if item.get("simulation_image_url")),
    )
    return augmented


def analyze_face_with_runpod(*, image_bytes: bytes | None = None, image_url: str | None = None) -> dict | None:
    """Call RunPod with action=analyze_face. Returns dict with face_shape/golden_ratio_score or None on failure."""
    if not _runpod_enabled():
        return None

    payload: dict = {"action": "analyze_face"}
    if image_bytes:
        payload["image_base64"] = base64.b64encode(image_bytes).decode("ascii")
    elif image_url and image_url.startswith(("http://", "https://")):
        payload["image_url"] = image_url
    else:
        logger.warning("[analyze_face_runpod] no valid image provided — image_bytes=%s image_url=%s", bool(image_bytes), bool(image_url))
        return None

    remote = _post_runpod(payload)
    if not remote:
        logger.warning("[analyze_face_runpod] empty response from RunPod")
        return None

    face_shape = remote.get("face_shape")
    golden_ratio_score = remote.get("golden_ratio_score")
    if not face_shape and golden_ratio_score is None:
        logger.warning("[analyze_face_runpod] no face data in response. remote_keys=%s", sorted(remote.keys()))
        return None

    logger.info("[analyze_face_runpod] face_shape=%s golden_ratio_score=%s", face_shape, golden_ratio_score)
    return {
        "face_shape": face_shape,
        "golden_ratio_score": golden_ratio_score,
    }


def simulate_face_analysis(*, image_url: str | None = None, image_bytes: bytes | None = None) -> dict:
    payload = {"image_url": image_url}
    if image_bytes is not None:
        payload["image_base64"] = base64.b64encode(image_bytes).decode("ascii")
    remote = _request_service("POST", "/internal/analyze-face", payload)
    normalized = _normalize_analysis_payload(remote, fallback_image_url=image_url)
    if normalized:
        logger.info(
            "[ai_face_analysis] provider=service remote_success=True request_id=%s face_shape=%s",
            (normalized.get("response_meta") or {}).get("request_id"),
            normalized.get("face_shape"),
        )
        return normalized
    logger.info(
        "[ai_face_analysis] provider=%s remote_success=False fallback=local_mock",
        _ai_provider(),
    )
    return {
        "face_shape": "Oval",
        "golden_ratio_score": 0.92,
        "image_url": image_url,
    }


def _emit_runpod_direct_primary_skipped(reason: str, **details) -> None:
    logger.warning(
        "[runpod_direct_primary_skipped] reason=%s %s",
        reason,
        " ".join(f"{k}={v}" for k, v in details.items()),
    )


def _runpod_direct_outcome_snapshot(*, status: str, reason: str | None, invoked: bool) -> dict:
    return {
        "status": status,
        "reason": reason,
        "invoked": invoked,
    }


def _attach_runpod_direct_outcome(items: list[dict], outcome: dict | None) -> list[dict]:
    if not outcome or not items:
        return items

    snapshot = _runpod_direct_outcome_snapshot(
        status=str(outcome.get("status") or "unknown"),
        reason=(str(outcome.get("reason")) if outcome.get("reason") else None),
        invoked=bool(outcome.get("invoked")),
    )
    enriched_items: list[dict] = []
    for item in items:
        enriched = dict(item)
        reasoning_snapshot = dict(enriched.get("reasoning_snapshot") or {})
        reasoning_snapshot["runpod_direct"] = dict(snapshot)
        enriched["reasoning_snapshot"] = reasoning_snapshot
        enriched_items.append(enriched)
    return enriched_items


def _runpod_payload_summary(remote: dict) -> dict:
    recommendations = remote.get("recommendations")
    results = remote.get("results")
    return {
        "remote_keys": sorted(remote.keys()),
        "recommendation_count": len(recommendations) if isinstance(recommendations, list) else 0,
        "result_count": len(results) if isinstance(results, list) else 0,
        "has_traceback": bool(remote.get("traceback") or remote.get("error")),
    }


def _generate_runpod_recommendation_batch_details(
    *,
    client_id: int | None,
    survey_data: dict | None,
    analysis_data: dict,
    styles_by_id: dict[int, object] | None,
) -> dict:
    image_payload = _build_runpod_image_payload(analysis_data)
    face_ratios = _build_face_ratios(analysis_data)
    if not image_payload or not face_ratios:
        _emit_runpod_direct_primary_skipped(
            "missing_required_payload",
            has_image_payload=bool(image_payload),
            has_face_ratios=bool(face_ratios),
            has_image_url=bool(str(analysis_data.get("image_url") or "").strip()),
            has_image_base64=bool(str(analysis_data.get("image_base64") or "").strip()),
            has_landmark_snapshot=bool(analysis_data.get("landmark_snapshot")),
        )
        return {
            "status": "skipped",
            "reason": "missing_required_payload",
            "invoked": False,
            "items": None,
        }

    runpod_payload = {
        **image_payload,
        "face_ratios": face_ratios,
        "top_k": 5,
        "return_base64": True,
    }
    preference = _build_runpod_preference_payload(survey_data)
    preference_text = _build_preference_text(survey_data)
    if preference:
        runpod_payload["preference"] = preference
    if preference_text:
        runpod_payload["preference_text"] = preference_text
    color_text = (survey_data or {}).get("hair_colour")
    if color_text:
        runpod_payload["color_text"] = color_text

    remote = _post_runpod(runpod_payload)
    if not remote:
        _emit_runpod_direct_primary_skipped("empty_runpod_response", payload_keys=sorted(runpod_payload.keys()))
        return {
            "status": "failed",
            "reason": "empty_runpod_response",
            "invoked": True,
            "items": None,
        }

    summary = _runpod_payload_summary(remote)
    logger.info(
        "[runpod_direct_primary_response] client_id=%s remote_keys=%s recommendation_count=%s result_count=%s has_traceback=%s",
        client_id,
        summary["remote_keys"],
        summary["recommendation_count"],
        summary["result_count"],
        summary["has_traceback"],
    )
    normalized = _normalize_runpod_direct_items(client_id=client_id, remote=remote, styles_by_id=styles_by_id)
    if normalized is None:
        _emit_runpod_direct_primary_skipped(
            "normalization_failed",
            remote_keys=sorted(remote.keys()),
            recommendation_count=len(remote.get("recommendations") or []) if isinstance(remote.get("recommendations"), list) else 0,
            result_count=len(remote.get("results") or []) if isinstance(remote.get("results"), list) else 0,
        )
        return {
            "status": "failed",
            "reason": "normalization_failed",
            "invoked": True,
            "items": None,
        }

    return {
        "status": "completed",
        "reason": None,
        "invoked": True,
        "items": normalized,
    }


def generate_recommendation_batch(
    *,
    client_id: int,
    survey_data: dict | None,
    analysis_data: dict,
    styles_by_id: dict[int, object] | None = None,
    scoring_weights: ScoringWeights | None = None,
) -> list[dict]:
    scoring_weights = scoring_weights or DEFAULT_SCORING_WEIGHTS
    provider = _ai_provider()
    runpod_direct_outcome = None
    if provider == "service":
        remote = _request_service(
            "POST",
            "/internal/generate-simulations",
            {
                "client_id": client_id,
                "survey_data": survey_data or {},
                "analysis_data": analysis_data,
                "scoring_weights": scoring_weights.as_dict(),
            },
        )
        normalized_items = _normalize_simulation_items(remote)
        if normalized_items is not None:
            logger.info(
                "[ai_recommendations] provider=service remote_success=True client_id=%s item_count=%s request_id=%s",
                client_id,
                len(normalized_items),
                ((normalized_items[0].get("response_meta") or {}) if normalized_items else {}).get("request_id"),
            )
            return normalized_items
        logger.info(
            "[ai_recommendations] provider=service remote_success=False fallback=local_scoring client_id=%s",
            client_id,
        )

    survey = SimpleNamespace(client_id=client_id, **(survey_data or {}))
    analysis = SimpleNamespace(**analysis_data)
    items = score_recommendations(
        survey=survey,
        analysis=analysis,
        styles_by_id=styles_by_id,
        scoring_weights=scoring_weights,
    )

    if provider == "runpod":
        items = _augment_items_with_runpod(items=items, survey_data=survey_data, analysis_data=analysis_data)
        augmented_count = sum(1 for item in items if item.get("simulation_image_url"))
        logger.info(
            "[ai_recommendations] provider=runpod client_id=%s item_count=%s augmented_items=%s",
            client_id,
            len(items),
            augmented_count,
        )
    else:
        logger.info(
            "[ai_recommendations] provider=local client_id=%s item_count=%s",
            client_id,
            len(items),
        )
    return items


def explain_style(*, card: dict) -> dict:
    remote = _request_service("POST", "/internal/explain-style", {"card": card})
    normalized = _normalize_explain_style_payload(remote, card=card)
    if normalized:
        return normalized
    return {
        "style_id": card.get("style_id"),
        "style_name": card.get("style_name"),
        "sample_image_url": card.get("sample_image_url"),
        "simulation_image_url": card.get("simulation_image_url"),
        "llm_explanation": card.get("llm_explanation"),
        "keywords": card.get("keywords", []),
    }
