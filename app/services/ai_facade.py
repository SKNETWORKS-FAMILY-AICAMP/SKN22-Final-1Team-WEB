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
    return os.environ.get("MIRRAI_AI_SERVICE_URL", "").rstrip("/")


def _internal_api_token() -> str:
    return os.environ.get("MIRRAI_INTERNAL_API_TOKEN", "").strip()


def _legacy_internal_api_key() -> str:
    return os.environ.get("MIRRAI_INTERNAL_API_KEY", "").strip()


def _service_api_version() -> str:
    return os.environ.get("MIRRAI_AI_API_VERSION", "").strip()


def _runpod_base_url() -> str:
    return os.environ.get("RUNPOD_BASE_URL", "https://api.runpod.ai/v2").rstrip("/")


def _runpod_api_key() -> str:
    return os.environ.get("RUNPOD_API_KEY", "").strip()


def _runpod_endpoint_id() -> str:
    for env_name in ("RUNPOD_ENDPOINT_ID", "STABLE_DIFFUSION_ENDPOINT", "RUNPOD_TRENDS_ENDPOINT_ID"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    return ""


def _runpod_health_timeout() -> tuple[int, int]:
    read_timeout = int(os.environ.get("MIRRAI_AI_HEALTH_TIMEOUT", "5"))
    return (3, max(3, read_timeout))


def _service_timeout() -> int:
    return max(3, int(os.environ.get("MIRRAI_AI_SERVICE_TIMEOUT", "5")))


def _health_cache_seconds() -> int:
    return max(0, int(os.environ.get("MIRRAI_AI_HEALTH_CACHE_SECONDS", "15")))


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
        return None
    output = payload.get("output")
    if isinstance(output, dict):
        return output
    if any(key in payload for key in ("results", "recommendations", "cuda", "status")):
        return payload
    return None


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
        return _extract_runpod_output(response.json())
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
            error_code = parsed.get("error_code")
            retryable = parsed.get("retryable")
            message = parsed.get("message") or parsed.get("detail") or message
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
        if status == "success" or (allow_partial_success and status == "partial_success"):
            normalized = dict(data)
            partial_failures = payload.get("partial_failures")
            if allow_partial_success and status == "partial_success" and isinstance(partial_failures, list):
                normalized["partial_failures"] = list(partial_failures)
            normalized["service_status"] = status
            return _with_response_meta(normalized, payload)
        if status == "error":
            logger.warning(
                "AI service returned an error payload. error_code=%s message=%s retryable=%s",
                payload.get("error_code"),
                payload.get("message"),
                payload.get("retryable"),
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
    cached_payload = _AI_HEALTH_CACHE.get("payload")
    expires_at = float(_AI_HEALTH_CACHE.get("expires_at") or 0.0)

    if use_cache and cache_seconds > 0 and isinstance(cached_payload, dict) and now < expires_at:
        payload = dict(cached_payload)
        payload["cached"] = True
        return payload

    payload = _compute_ai_health()
    payload["cached"] = False
    if cache_seconds > 0:
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
    return payload


def _build_preference_text(survey_data: dict | None) -> str | None:
    survey_data = survey_data or {}
    parts = [
        str(survey_data.get("target_length") or "").strip(),
        str(survey_data.get("target_vibe") or "").strip(),
        str(survey_data.get("scalp_type") or "").strip(),
        str(survey_data.get("hair_colour") or "").strip(),
        str(survey_data.get("budget_range") or "").strip(),
    ]
    text = ", ".join(part for part in parts if part)
    return text or None


def _build_face_ratios(analysis_data: dict | None) -> dict | None:
    analysis_data = analysis_data or {}
    snapshot = analysis_data.get("landmark_snapshot") or {}
    face_bbox = snapshot.get("face_bbox") or {}
    landmarks = snapshot.get("landmarks") or {}
    if not face_bbox:
        return None

    face_height = float(face_bbox.get("height") or 0)
    face_width = float(face_bbox.get("width") or 0)
    if face_height <= 0 or face_width <= 0:
        return None

    left_eye = (landmarks.get("left_eye") or {}).get("point")
    right_eye = (landmarks.get("right_eye") or {}).get("point")
    mouth_center = (landmarks.get("mouth_center") or {}).get("point")
    chin_center = (landmarks.get("chin_center") or {}).get("point")
    if not (left_eye and right_eye and mouth_center and chin_center):
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


def _augment_items_with_runpod(
    *,
    items: list[dict],
    survey_data: dict | None,
    analysis_data: dict,
) -> list[dict]:
    if _ai_provider() != "runpod":
        return items

    image = analysis_data.get("image_url")
    face_ratios = _build_face_ratios(analysis_data)
    if not image or not face_ratios:
        return items

    runpod_payload = {
        "image": image,
        "face_ratios": face_ratios,
        "top_k": min(len(items), 5),
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
        return items

    results = remote.get("results")
    if not isinstance(results, list) or not results:
        return items

    recommendations = remote.get("recommendations")
    if not isinstance(recommendations, list):
        recommendations = []

    rag_context_excerpt = _rag_context_excerpt(remote.get("rag_context"))
    build_tag = str(remote.get("build_tag") or "").strip() or None
    runpod_runtime = remote.get("runpod") if isinstance(remote.get("runpod"), dict) else {}

    augmented: list[dict] = []
    for index, item in enumerate(items):
        enriched = dict(item)
        if index < len(results):
            result = results[index] or {}
            recommendation_meta = _match_runpod_recommendation(
                recommendations=recommendations,
                index=index,
                result=result,
            )
            image_base64 = result.get("image_base64")
            if image_base64:
                data_url = f"data:image/png;base64,{image_base64}"
                enriched["simulation_image_url"] = data_url
                enriched["synthetic_image_url"] = data_url
            snapshot = dict(enriched.get("reasoning_snapshot") or {})
            runpod_snapshot = {
                "provider": "runpod",
                "clip_score": result.get("clip_score"),
                "mask_used": result.get("mask_used"),
                "elapsed_seconds": remote.get("elapsed_seconds"),
                "recommended_style": result.get("recommended_style"),
                "build_tag": build_tag,
                "runtime": runpod_runtime,
                "rag_context_excerpt": rag_context_excerpt,
            }
            if recommendation_meta:
                runpod_snapshot["recommendation"] = recommendation_meta
                runpod_snapshot["face_shape_detected"] = recommendation_meta.get("face_shape_detected")
                runpod_snapshot["golden_ratio_score"] = recommendation_meta.get("golden_ratio_score")
                runpod_snapshot["face_shapes"] = recommendation_meta.get("face_shapes")
                if recommendation_meta.get("description"):
                    enriched["llm_explanation"] = enriched.get("llm_explanation") or recommendation_meta.get("description")
                    enriched["style_description"] = enriched.get("style_description") or recommendation_meta.get("description")
            snapshot["runpod"] = runpod_snapshot
            enriched["reasoning_snapshot"] = snapshot
        augmented.append(enriched)
    return augmented


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
    items = _augment_items_with_runpod(items=items, survey_data=survey_data, analysis_data=analysis_data)
    if provider == "runpod":
        augmented_count = sum(
            1 for item in items if isinstance((item.get("reasoning_snapshot") or {}).get("runpod"), dict)
        )
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
