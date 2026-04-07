import base64
import json
import logging
import os
import re
import sys
import time
from math import dist
from types import SimpleNamespace

import requests

from app.api.v1.recommendation_logic import (
    DEFAULT_SCORING_WEIGHTS,
    ScoringWeights,
    STYLE_CATALOG,
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

RUNPOD_QUEUE_STATUSES = {"IN_QUEUE", "IN_PROGRESS"}
FAILED_RUNPOD_STATUSES = {"FAILED", "CANCELLED", "TIMED_OUT"}


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


def _runpod_sync_timeout_seconds() -> int:
    return max(15, int(os.environ.get("MIRRAI_RUNPOD_SYNC_TIMEOUT", "180")))


def _runpod_poll_interval_seconds() -> float:
    return max(0.5, float(os.environ.get("MIRRAI_RUNPOD_POLL_INTERVAL", "2.0")))


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
    probe_payload_json = os.environ.get("MIRRAI_RUNPOD_PROBE_PAYLOAD_JSON", "").strip()
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
        "runpod_probe_payload_configured": bool(probe_payload_json),
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


def _runpod_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_runpod_api_key()}",
        "Content-Type": "application/json",
    }


def _classify_runpod_request_exception(exc: requests.RequestException) -> tuple[str, str]:
    response = getattr(exc, "response", None)
    if response is not None:
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code in {401, 403}:
            return "auth_error", f"RunPod authentication failed with status={status_code}."
        return "failed", f"RunPod request failed with status={status_code}."
    return "network_error", str(exc) or "RunPod request failed."


def _runpod_probe_payload() -> dict | None:
    raw = os.environ.get("MIRRAI_RUNPOD_PROBE_PAYLOAD_JSON", "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        logger.warning("RunPod probe payload env is not valid JSON.")
        return None
    if not isinstance(parsed, dict):
        logger.warning("RunPod probe payload env must be a JSON object.")
        return None
    return parsed


def _has_runpod_recommendation_metadata(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    recommendations = payload.get("recommendations")
    if not isinstance(recommendations, list):
        return False
    for item in recommendations:
        if not isinstance(item, dict):
            continue
        if item.get("face_shape_detected") and item.get("golden_ratio_score") is not None:
            return True
    return False


def _poll_runpod_job_output(*, job_id: str, timeout_seconds: int, poll_interval: float) -> dict:
    status_url = f"{_runpod_base_url()}/{_runpod_endpoint_id()}/status/{job_id}"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = requests.get(
                status_url,
                headers={"Authorization": f"Bearer {_runpod_api_key()}"},
                timeout=min(timeout_seconds, 60),
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            state, message = _classify_runpod_request_exception(exc)
            logger.warning("RunPod job %s polling failed: %s", job_id, message)
            return {
                "state": state,
                "message": message,
                "job_id": job_id,
                "job_status": None,
                "output": None,
                "last_error_code": "RUNPOD_STATUS_REQUEST_FAILED",
            }
        except ValueError:
            logger.warning("RunPod job %s polling returned invalid JSON", job_id)
            return {
                "state": "failed",
                "message": "RunPod status polling returned invalid JSON.",
                "job_id": job_id,
                "job_status": None,
                "output": None,
                "last_error_code": "RUNPOD_STATUS_INVALID_JSON",
            }
        status = str((payload or {}).get("status") or "").upper()
        if status == "COMPLETED":
            output_url = payload.get("output_url")
            if output_url:
                try:
                    output_response = requests.get(str(output_url), timeout=min(timeout_seconds, 120))
                    output_response.raise_for_status()
                    fetched = output_response.json()
                except requests.RequestException as exc:
                    state, message = _classify_runpod_request_exception(exc)
                    logger.warning("RunPod job %s output fetch failed: %s", job_id, message)
                    return {
                        "state": state,
                        "message": message,
                        "job_id": job_id,
                        "job_status": status,
                        "output": None,
                        "last_error_code": "RUNPOD_OUTPUT_FETCH_FAILED",
                    }
                except ValueError:
                    logger.warning("RunPod job %s output fetch returned invalid JSON", job_id)
                    return {
                        "state": "failed",
                        "message": "RunPod output fetch returned invalid JSON.",
                        "job_id": job_id,
                        "job_status": status,
                        "output": None,
                        "last_error_code": "RUNPOD_OUTPUT_INVALID_JSON",
                    }
                extracted = _extract_runpod_output(fetched if isinstance(fetched, dict) else {"output": fetched})
                return {
                    "state": "completed",
                    "message": "RunPod job completed after polling.",
                    "job_id": job_id,
                    "job_status": status,
                    "output": extracted,
                    "last_error_code": None,
                }
            return {
                "state": "completed",
                "message": "RunPod job completed after polling.",
                "job_id": job_id,
                "job_status": status,
                "output": _extract_runpod_output(payload),
                "last_error_code": None,
            }
        if status in FAILED_RUNPOD_STATUSES:
            logger.warning("RunPod job %s failed with status=%s error=%s output=%s", job_id, status, payload.get("error"), payload.get("output"))
            return {
                "state": "failed",
                "message": str(payload.get("error") or f"RunPod job failed with status={status}."),
                "job_id": job_id,
                "job_status": status,
                "output": None,
                "last_error_code": f"RUNPOD_JOB_{status}",
            }
        time.sleep(poll_interval)
    logger.warning("RunPod job %s did not complete within %s seconds", job_id, timeout_seconds)
    return {
        "state": "timeout",
        "message": f"RunPod job did not complete within {timeout_seconds} seconds.",
        "job_id": job_id,
        "job_status": "TIMEOUT",
        "output": None,
        "last_error_code": "RUNPOD_SYNC_TIMEOUT",
    }


def _runpod_request_details(input_payload: dict, *, sync: bool = True, timeout: tuple[int, int] | None = None) -> dict:
    if not _runpod_enabled():
        return {
            "state": "misconfigured",
            "message": "RunPod API key or endpoint id is missing.",
            "job_id": None,
            "job_status": None,
            "output": None,
            "last_error_code": "RUNPOD_NOT_CONFIGURED",
        }

    route = "runsync" if sync else "run"
    request_timeout = timeout or (5, 120)
    url = f"{_runpod_base_url()}/{_runpod_endpoint_id()}/{route}"
    try:
        response = requests.post(
            url,
            json={"input": input_payload},
            headers=_runpod_headers(),
            timeout=request_timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        state, message = _classify_runpod_request_exception(exc)
        logger.warning("RunPod request failed: %s", message)
        return {
            "state": state,
            "message": message,
            "job_id": None,
            "job_status": None,
            "output": None,
            "last_error_code": "RUNPOD_REQUEST_FAILED",
        }
    except ValueError:
        logger.warning("RunPod request returned invalid JSON")
        return {
            "state": "failed",
            "message": "RunPod request returned invalid JSON.",
            "job_id": None,
            "job_status": None,
            "output": None,
            "last_error_code": "RUNPOD_INVALID_JSON",
        }

    extracted = _extract_runpod_output(payload)
    status = str((payload or {}).get("status") or "").upper()
    job_id = str((payload or {}).get("id") or "").strip() or None
    if sync and status in RUNPOD_QUEUE_STATUSES:
        if not job_id:
            logger.warning("RunPod sync response queued without job id: %s", payload)
            return {
                "state": "queued",
                "message": "RunPod sync response is queued without a job id.",
                "job_id": None,
                "job_status": status,
                "output": extracted,
                "last_error_code": "RUNPOD_QUEUE_WITHOUT_JOB_ID",
            }
        timeout_seconds = max(
            _runpod_sync_timeout_seconds(),
            int(request_timeout[1] if len(request_timeout) > 1 else request_timeout[0]),
        )
        polled = _poll_runpod_job_output(
            job_id=job_id,
            timeout_seconds=timeout_seconds,
            poll_interval=_runpod_poll_interval_seconds(),
        )
        polled.setdefault("job_id", job_id)
        polled.setdefault("job_status", status)
        return polled
    if status in FAILED_RUNPOD_STATUSES:
        return {
            "state": "failed",
            "message": str(payload.get("error") or f"RunPod request failed with status={status}."),
            "job_id": job_id,
            "job_status": status,
            "output": extracted,
            "last_error_code": f"RUNPOD_REQUEST_{status}",
        }
    return {
        "state": "completed",
        "message": "RunPod request completed.",
        "job_id": job_id,
        "job_status": status or None,
        "output": extracted,
        "last_error_code": None,
    }


def _post_runpod(input_payload: dict, *, sync: bool = True, timeout: tuple[int, int] | None = None) -> dict | None:
    details = _runpod_request_details(input_payload, sync=sync, timeout=timeout)
    if details.get("state") != "completed":
        logger.warning("Falling back after RunPod call failure: %s", details.get("message"))
    return details.get("output")


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
        details = _runpod_request_details({"action": "health_check"}, timeout=_runpod_health_timeout())
        payload = details.get("output")
        state = str(details.get("state") or "unknown")
        if isinstance(payload, dict):
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
                "connectivity_state": state,
                "last_error_code": details.get("last_error_code"),
            }
            logger.info("[ai_health] provider=runpod status=%s message=%s", result["status"], result["message"])
            return result
        status = "offline" if state in {"network_error", "timeout", "failed", "auth_error"} else state
        result = {
            "status": status,
            "mode": "runpod",
            "message": details.get("message") or "RunPod health check failed.",
            "connectivity_state": state,
            "last_error_code": details.get("last_error_code"),
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
    if config.get("resolved_provider") == "runpod":
        return "runpod_inference_metadata"
    if config.get("service_enabled"):
        return "service_remote"
    return "disabled"


def _recommendation_runtime_mode(config: dict) -> str:
    resolved_provider = config.get("resolved_provider")
    if resolved_provider == "service":
        return "service_remote"
    if resolved_provider == "runpod":
        return "runpod_direct_primary_with_sync_polling"
    return "local_scoring_fallback"


def build_runpod_inference_probe_snapshot() -> dict:
    config = get_ai_runtime_config_snapshot()
    if config.get("resolved_provider") != "runpod":
        return {
            "provider": config.get("resolved_provider"),
            "status": "skipped",
            "inference_status": "skipped",
            "sync_contract_state": "not_applicable",
            "metadata_state": "unknown",
            "queue_state": "not_applicable",
            "message": "RunPod is not the active provider.",
            "last_error_code": None,
        }

    probe_payload = _runpod_probe_payload()
    if not probe_payload:
        return {
            "provider": "runpod",
            "status": "skipped",
            "inference_status": "not_configured",
            "sync_contract_state": "unknown",
            "metadata_state": "unknown",
            "queue_state": "unknown",
            "message": "RunPod probe payload is not configured.",
            "last_error_code": "RUNPOD_PROBE_PAYLOAD_NOT_CONFIGURED",
        }

    started_at = time.monotonic()
    details = _runpod_request_details(probe_payload, sync=True, timeout=(5, _runpod_sync_timeout_seconds()))
    elapsed_ms = int((time.monotonic() - started_at) * 1000)
    state = str(details.get("state") or "unknown")
    output = details.get("output")
    metadata_present = _has_runpod_recommendation_metadata(output)

    inference_status = state
    sync_contract_state = "satisfied" if state == "completed" else "degraded"
    metadata_state = "present" if metadata_present else "missing"
    queue_state = "resolved"

    if state == "completed" and not metadata_present:
        inference_status = "metadata_missing"
        metadata_state = "missing"
        sync_contract_state = "degraded"
    elif state == "completed":
        inference_status = "completed"
    elif state in RUNPOD_QUEUE_STATUSES:
        queue_state = state.lower()
    elif state == "timeout":
        queue_state = "stuck"
    elif state == "skipped":
        queue_state = "unknown"

    if state not in {"completed", "queued", "timeout"}:
        queue_state = "not_applicable"

    return {
        "provider": "runpod",
        "status": "ok" if state == "completed" and metadata_present else inference_status,
        "inference_status": inference_status,
        "sync_contract_state": sync_contract_state,
        "metadata_state": metadata_state,
        "queue_state": queue_state,
        "message": details.get("message"),
        "last_error_code": details.get("last_error_code"),
        "elapsed_ms": elapsed_ms,
        "job_id": details.get("job_id"),
        "job_status": details.get("job_status"),
    }


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
                "connectivity_state": health.get("connectivity_state") or status,
                "last_error_code": health.get("last_error_code"),
            }
        )

    overall_state = "healthy"
    if online_count == 0 and offline_count == attempts:
        overall_state = "offline"
    elif online_count == 0:
        overall_state = "fallback_only"
    elif offline_count > 0:
        overall_state = "unstable"

    inference_probe = build_runpod_inference_probe_snapshot()
    warnings: list[str] = []
    if config.get("resolved_provider") == "runpod" and online_count and offline_count:
        warnings.append("runpod_health_flaky")
    if config.get("resolved_provider") == "runpod" and online_count == 0:
        warnings.append("runpod_health_unavailable")
    if config.get("resolved_provider") == "local":
        warnings.append("remote_model_not_active")
    if inference_probe.get("inference_status") == "not_configured":
        warnings.append("runpod_probe_payload_not_configured")
    if inference_probe.get("inference_status") == "timeout":
        warnings.append("runpod_sync_timeout")
    if inference_probe.get("inference_status") == "metadata_missing":
        warnings.append("runpod_metadata_missing")

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
            "connectivity_state": "online" if online_count else "offline",
            "inference_status": inference_probe.get("inference_status"),
            "sync_contract_state": inference_probe.get("sync_contract_state"),
            "metadata_state": inference_probe.get("metadata_state"),
            "queue_state": inference_probe.get("queue_state"),
            "last_error_code": inference_probe.get("last_error_code"),
            "last_error_message": inference_probe.get("message"),
        },
        "probes": probes,
        "inference_probe": inference_probe,
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




def _emit_runpod_direct_primary_skipped(reason: str, **details) -> None:
    detail_text = " ".join(f"{key}={value!r}" for key, value in details.items())
    message = f"[runpod_direct_primary_skipped] reason={reason}"
    if detail_text:
        message = f"{message} {detail_text}"
    logger.warning(message)
    print(message, file=sys.stderr, flush=True)

def _build_face_ratios(analysis_data: dict | None) -> dict | None:
    analysis_data = analysis_data or {}
    snapshot = analysis_data.get("landmark_snapshot") or {}
    face_bbox = snapshot.get("face_bbox") or {}
    landmarks = snapshot.get("landmarks") or {}
    if not face_bbox:
        _emit_runpod_direct_primary_skipped("missing_face_bbox", analysis_keys=sorted(analysis_data.keys()), snapshot_keys=sorted(snapshot.keys()))
        return None

    face_height = float(face_bbox.get("height") or 0)
    face_width = float(face_bbox.get("width") or 0)
    if face_height <= 0 or face_width <= 0:
        _emit_runpod_direct_primary_skipped("invalid_face_bbox_dimensions", face_height=face_height, face_width=face_width, face_bbox=face_bbox)
        return None

    left_eye = (landmarks.get("left_eye") or {}).get("point")
    right_eye = (landmarks.get("right_eye") or {}).get("point")
    mouth_center = (landmarks.get("mouth_center") or {}).get("point")
    chin_center = (landmarks.get("chin_center") or {}).get("point")
    if not (left_eye and right_eye and mouth_center and chin_center):
        missing_parts = [
            name
            for name, value in (
                ("left_eye", left_eye),
                ("right_eye", right_eye),
                ("mouth_center", mouth_center),
                ("chin_center", chin_center),
            )
            if not value
        ]
        _emit_runpod_direct_primary_skipped("missing_landmark_points", missing_parts=missing_parts, landmark_keys=sorted(landmarks.keys()))
        return None

    eye_distance = dist((left_eye["x"], left_eye["y"]), (right_eye["x"], right_eye["y"]))
    jaw_height = max(0.0, float(chin_center["y"]) - float(mouth_center["y"]))
    if eye_distance <= 0 or jaw_height <= 0:
        _emit_runpod_direct_primary_skipped("invalid_ratio_components", eye_distance=eye_distance, jaw_height=jaw_height)
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


def _runpod_candidate_maps(*, recommendation_meta: dict | None, result: dict | None) -> list[dict]:
    candidate_maps: list[dict] = []
    for candidate in (recommendation_meta, result):
        if not isinstance(candidate, dict):
            continue
        candidate_maps.append(candidate)
        for nested_key in (
            "recommended_style",
            "style",
            "hairstyle",
            "recommended_hairstyle",
            "output",
            "result",
            "simulation",
            "image",
            "metadata",
            "analysis",
        ):
            nested = candidate.get(nested_key)
            if isinstance(nested, dict):
                candidate_maps.append(nested)
    return candidate_maps


def _runpod_scalar_candidates(*, candidate_maps: list[dict], keys: tuple[str, ...]) -> list[object]:
    values: list[object] = []
    for candidate in candidate_maps:
        for key in keys:
            value = candidate.get(key)
            if value not in (None, "", []):
                values.append(value)
    return values


def _rag_context_excerpt(value: object, *, limit: int = 280) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _extract_runpod_image_reference(*, result: dict, recommendation_meta: dict | None) -> tuple[str | None, str | None, str | None]:
    candidate_maps = _runpod_candidate_maps(recommendation_meta=recommendation_meta, result=result)

    for candidate in candidate_maps:
        for url_key, expires_key in (
            ("simulation_image_url", "simulation_image_url_expires_at"),
            ("synthetic_image_url", "synthetic_image_url_expires_at"),
            ("image_url", "image_url_expires_at"),
            ("generated_image_url", "generated_image_url_expires_at"),
            ("simulation_url", "simulation_url_expires_at"),
            ("result_image_url", "result_image_url_expires_at"),
            ("output_image_url", "output_image_url_expires_at"),
        ):
            value = str(candidate.get(url_key) or "").strip()
            if value:
                return value, str(candidate.get(expires_key) or "").strip() or None, "signed_url"
        raw_image_value = candidate.get("image")
        if isinstance(raw_image_value, str) and raw_image_value.strip().startswith(("http://", "https://", "data:image/")):
            return raw_image_value.strip(), None, ("data_url" if raw_image_value.strip().startswith("data:image/") else "signed_url")

    for image_base64 in _runpod_scalar_candidates(
        candidate_maps=candidate_maps,
        keys=("image_base64", "simulation_image_base64", "synthetic_image_base64", "generated_image_base64", "base64"),
    ):
        text = str(image_base64 or "").strip()
        if not text:
            continue
        if text.startswith("data:image/"):
            return text, None, "data_url"
        return f"data:image/png;base64,{text}", None, "base64_data_url"

    return None, None, None


def _normalize_style_token(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "").replace("_", "").replace(" ", "")


def _style_alias_tokens(*, style_id: int, styles_by_id: dict[int, object] | None) -> set[str]:
    styles_by_id = styles_by_id or {}
    aliases: set[str] = set()
    style = styles_by_id.get(style_id)
    profile = _style_profile_for_id(style_id)
    for candidate in (
        getattr(style, "name", None),
        getattr(style, "style_name", None),
        getattr(style, "vibe", None),
        (profile.fallback_name if profile else None),
    ):
        token = _normalize_style_token(candidate)
        if token:
            aliases.add(token)
    if profile:
        for keyword in profile.keywords:
            token = _normalize_style_token(keyword)
            if token:
                aliases.add(token)
    return aliases


def _score_style_alias_match(*, candidate_token: str, alias_token: str) -> int:
    if not candidate_token or not alias_token:
        return 0
    if candidate_token == alias_token:
        return 1000 + len(alias_token)
    if len(alias_token) >= 4 and alias_token in candidate_token:
        return 200 + len(alias_token)
    if len(candidate_token) >= 4 and candidate_token in alias_token:
        return 100 + len(candidate_token)
    return 0


def _coerce_runpod_style_id(candidate: object, *, styles_by_id: dict[int, object] | None) -> int | None:
    styles_by_id = styles_by_id or {}
    try:
        style_id = int(candidate)
    except (TypeError, ValueError):
        style_id = None
    if style_id is not None and (style_id in styles_by_id or _style_profile_for_id(style_id) is not None):
        return style_id

    text = str(candidate or "").strip()
    if not text:
        return None
    digit_matches = re.findall(r"\d+", text)
    for match in reversed(digit_matches):
        try:
            parsed = int(match)
        except ValueError:
            continue
        if parsed in styles_by_id or _style_profile_for_id(parsed) is not None:
            return parsed
    return None


def _style_profile_for_id(style_id: int):
    return next((profile for profile in STYLE_CATALOG if profile.style_id == style_id), None)


def _style_reference_for_id(*, style_id: int, styles_by_id: dict[int, object] | None) -> dict:
    styles_by_id = styles_by_id or {}
    style = styles_by_id.get(style_id)
    profile = _style_profile_for_id(style_id)
    style_name = (
        getattr(style, "name", None)
        or getattr(style, "style_name", None)
        or (profile.fallback_name if profile else f"Style {style_id}")
    )
    style_description = (
        getattr(style, "description", None)
        or (profile.fallback_description if profile else "")
        or ""
    )
    sample_image_url = getattr(style, "image_url", None) or (profile.fallback_sample_image_url if profile else None)
    keywords = list(profile.keywords) if profile else ([getattr(style, "vibe", None)] if getattr(style, "vibe", None) else [])
    return {
        "style_id": style_id,
        "style_name": style_name,
        "style_description": style_description,
        "sample_image_url": sample_image_url,
        "keywords": keywords,
    }


def _resolve_runpod_style_id(
    *,
    recommendation_meta: dict | None,
    result: dict,
    styles_by_id: dict[int, object] | None,
) -> int | None:
    styles_by_id = styles_by_id or {}
    candidate_maps = _runpod_candidate_maps(recommendation_meta=recommendation_meta, result=result)
    numeric_candidates = _runpod_scalar_candidates(
        candidate_maps=candidate_maps,
        keys=("style_id", "hairstyle_id", "backend_style_id", "id", "style_code", "styleCode"),
    )
    for candidate in numeric_candidates:
        style_id = _coerce_runpod_style_id(candidate, styles_by_id=styles_by_id)
        if style_id is not None:
            return style_id

    style_name_candidates = _runpod_scalar_candidates(
        candidate_maps=candidate_maps,
        keys=("style_name", "hairstyle_name", "recommended_style_name", "name", "label", "title"),
    )
    best_style_id = None
    best_score = 0
    score_tie = False
    known_style_ids = sorted({*styles_by_id.keys(), *(profile.style_id for profile in STYLE_CATALOG)})
    for candidate in style_name_candidates:
        candidate_token = _normalize_style_token(candidate)
        if not candidate_token:
            continue
        for style_id in known_style_ids:
            aliases = _style_alias_tokens(style_id=style_id, styles_by_id=styles_by_id)
            style_score = max((_score_style_alias_match(candidate_token=candidate_token, alias_token=alias) for alias in aliases), default=0)
            if style_score > best_score:
                best_style_id = style_id
                best_score = style_score
                score_tie = False
            elif style_score and style_score == best_score and best_style_id != style_id:
                score_tie = True
    if best_style_id is not None and not score_tie:
        return best_style_id
    return None


def _match_runpod_result(
    *,
    results: list[dict],
    index: int,
    recommendation_meta: dict | None,
) -> dict:
    if index < len(results) and isinstance(results[index], dict):
        return results[index]

    candidate_maps = _runpod_candidate_maps(recommendation_meta=recommendation_meta, result=None)
    style_id_candidates = {
        str(value).strip()
        for value in _runpod_scalar_candidates(
            candidate_maps=candidate_maps,
            keys=("style_id", "hairstyle_id", "backend_style_id", "id", "style_code", "styleCode"),
        )
        if str(value or "").strip()
    }
    style_name_candidates = {
        _normalize_style_token(value)
        for value in _runpod_scalar_candidates(
            candidate_maps=candidate_maps,
            keys=("style_name", "hairstyle_name", "recommended_style_name", "name", "label", "title"),
        )
        if _normalize_style_token(value)
    }
    for result in results:
        if not isinstance(result, dict):
            continue
        result_maps = _runpod_candidate_maps(recommendation_meta=None, result=result)
        result_ids = {
            str(value).strip()
            for value in _runpod_scalar_candidates(
                candidate_maps=result_maps,
                keys=("style_id", "hairstyle_id", "backend_style_id", "id", "style_code", "styleCode"),
            )
            if str(value or "").strip()
        }
        result_names = {
            _normalize_style_token(value)
            for value in _runpod_scalar_candidates(
                candidate_maps=result_maps,
                keys=("style_name", "hairstyle_name", "recommended_style_name", "name", "label", "title"),
            )
            if _normalize_style_token(value)
        }
        if style_id_candidates and (style_id_candidates & result_ids):
            return result
        if style_name_candidates and (style_name_candidates & result_names):
            return result
    return {}


def _normalize_runpod_direct_items(
    *,
    remote: dict,
    styles_by_id: dict[int, object] | None,
) -> list[dict] | None:
    recommendations = remote.get("recommendations")
    results = remote.get("results")
    if not isinstance(results, list):
        results = []
    if not isinstance(recommendations, list) or not recommendations:
        recommendations = [result for result in results if isinstance(result, dict)]
    if not recommendations:
        return None

    rag_context_excerpt = _rag_context_excerpt(remote.get("rag_context"))
    build_tag = str(remote.get("build_tag") or "").strip() or None
    runpod_runtime = remote.get("runpod") if isinstance(remote.get("runpod"), dict) else {}

    normalized_items: list[dict] = []
    skipped_style_matches = 0
    for index, recommendation_meta in enumerate(recommendations):
        if not isinstance(recommendation_meta, dict):
            continue
        result = _match_runpod_result(results=results, index=index, recommendation_meta=recommendation_meta)
        style_id = _resolve_runpod_style_id(
            recommendation_meta=recommendation_meta,
            result=result,
            styles_by_id=styles_by_id,
        )
        if style_id is None:
            skipped_style_matches += 1
            continue
        style_reference = _style_reference_for_id(style_id=style_id, styles_by_id=styles_by_id)
        image_reference, image_expires_at, image_transport = _extract_runpod_image_reference(
            result=result,
            recommendation_meta=recommendation_meta,
        )
        try:
            match_score = float(
                recommendation_meta.get("score")
                or recommendation_meta.get("recommendation_score")
                or (result.get("recommended_style") or {}).get("recommendation_score")
                or result.get("recommendation_score")
                or result.get("clip_score")
                or 0.0
            )
        except (TypeError, ValueError):
            match_score = 0.0
        summary = (
            recommendation_meta.get("description")
            or recommendation_meta.get("reason")
            or result.get("description")
            or result.get("reason")
            or style_reference["style_description"]
            or f"RunPod direct recommendation for {style_reference['style_name']}."
        )
        rank = recommendation_meta.get("rank") or result.get("rank") or (index + 1)
        try:
            rank = int(rank)
        except (TypeError, ValueError):
            rank = index + 1

        result_maps = _runpod_candidate_maps(recommendation_meta=recommendation_meta, result=result)
        runpod_snapshot = {
            "provider": "runpod",
            "clip_score": result.get("clip_score"),
            "mask_used": result.get("mask_used"),
            "elapsed_seconds": remote.get("elapsed_seconds"),
            "recommended_style": result.get("recommended_style"),
            "build_tag": build_tag,
            "runtime": runpod_runtime,
            "rag_context_excerpt": rag_context_excerpt,
            "recommendation": recommendation_meta,
            "face_shape_detected": next(
                (
                    value
                    for value in _runpod_scalar_candidates(
                        candidate_maps=result_maps,
                        keys=("face_shape_detected", "face_shape", "detected_face_shape"),
                    )
                    if str(value or "").strip()
                ),
                None,
            ),
            "golden_ratio_score": next(
                (
                    value
                    for value in _runpod_scalar_candidates(
                        candidate_maps=result_maps,
                        keys=("golden_ratio_score", "golden_ratio", "ratio_score"),
                    )
                    if value not in (None, "")
                ),
                None,
            ),
            "face_shapes": next(
                (
                    value
                    for value in _runpod_scalar_candidates(
                        candidate_maps=result_maps,
                        keys=("face_shapes",),
                    )
                    if value not in (None, "")
                ),
                None,
            ),
        }
        if image_transport:
            runpod_snapshot["image_transport"] = image_transport
        if image_expires_at:
            runpod_snapshot["simulation_image_url_expires_at"] = image_expires_at

        normalized_items.append(
            {
                "source": "generated",
                "style_id": style_reference["style_id"],
                "style_name": style_reference["style_name"],
                "style_description": style_reference["style_description"] or summary,
                "keywords": style_reference["keywords"],
                "sample_image_url": style_reference["sample_image_url"],
                "simulation_image_url": image_reference,
                "synthetic_image_url": image_reference,
                "llm_explanation": summary,
                "reasoning": summary,
                "reasoning_snapshot": {
                    "summary": summary,
                    "source": "runpod_direct_primary",
                    "remote_score": match_score,
                    "runpod": runpod_snapshot,
                },
                "match_score": match_score,
                "rank": rank,
            }
        )

    if not normalized_items:
        _emit_runpod_direct_primary_skipped("style_mapping_failed", recommendation_count=len(recommendations), result_count=len(results), skipped_style_matches=skipped_style_matches)
        return None

    normalized_items.sort(key=lambda item: (int(item.get("rank") or 999), -float(item.get("match_score") or 0.0)))
    return normalized_items[:5]


def _build_runpod_image_payload(analysis_data: dict) -> dict | None:
    image_url = str(analysis_data.get("image_url") or "").strip()
    if image_url:
        return {"image": image_url}

    image_base64 = str(analysis_data.get("image_base64") or "").strip()
    if image_base64:
        return {"image_base64": image_base64}

    return None


def _generate_runpod_recommendation_batch(
    *,
    survey_data: dict | None,
    analysis_data: dict,
    styles_by_id: dict[int, object] | None,
) -> list[dict] | None:
    image_payload = _build_runpod_image_payload(analysis_data)
    face_ratios = _build_face_ratios(analysis_data)
    if not image_payload or not face_ratios:
        _emit_runpod_direct_primary_skipped("missing_required_payload", has_image_payload=bool(image_payload), has_face_ratios=bool(face_ratios), has_image_url=bool(str(analysis_data.get("image_url") or "").strip()), has_image_base64=bool(str(analysis_data.get("image_base64") or "").strip()), has_landmark_snapshot=bool(analysis_data.get("landmark_snapshot")))
        return None

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
        return None
    normalized = _normalize_runpod_direct_items(remote=remote, styles_by_id=styles_by_id)
    if normalized is None:
        _emit_runpod_direct_primary_skipped("normalization_failed", remote_keys=sorted(remote.keys()), recommendation_count=len(remote.get("recommendations") or []) if isinstance(remote.get("recommendations"), list) else 0, result_count=len(remote.get("results") or []) if isinstance(remote.get("results"), list) else 0)
        return None
    return normalized


def _augment_items_with_runpod(
    *,
    items: list[dict],
    survey_data: dict | None,
    analysis_data: dict,
) -> list[dict]:
    if _ai_provider() != "runpod":
        return items

    image_payload = _build_runpod_image_payload(analysis_data)
    face_ratios = _build_face_ratios(analysis_data)
    if not image_payload or not face_ratios:
        return items

    runpod_payload = {
        **image_payload,
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
            image_reference, image_expires_at, image_transport = _extract_runpod_image_reference(
                result=result,
                recommendation_meta=recommendation_meta,
            )
            if image_reference:
                enriched["simulation_image_url"] = image_reference
                enriched["synthetic_image_url"] = image_reference
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
            if image_transport:
                runpod_snapshot["image_transport"] = image_transport
            if image_expires_at:
                runpod_snapshot["simulation_image_url_expires_at"] = image_expires_at
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
    raise RuntimeError(
        "simulate_face_analysis fallback is disabled. RunPod direct recommendation metadata is required."
    )


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
    if provider == "runpod":
        direct_items = _generate_runpod_recommendation_batch(
            survey_data=survey_data,
            analysis_data=analysis_data,
            styles_by_id=styles_by_id,
        )
        if direct_items is not None:
            logger.info(
                "[ai_recommendations] provider=runpod remote_success=True client_id=%s item_count=%s direct_primary=True",
                client_id,
                len(direct_items),
            )
            return direct_items

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
