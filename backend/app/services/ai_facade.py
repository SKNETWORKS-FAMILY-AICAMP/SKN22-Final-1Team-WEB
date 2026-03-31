import base64
import json
import logging
import os
import time
from math import dist
from types import SimpleNamespace
from urllib import error, request

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


def _runpod_enabled() -> bool:
    return bool(_runpod_api_key() and _runpod_endpoint_id())


def _ai_provider() -> str:
    configured = os.environ.get("MIRRAI_AI_PROVIDER", "").strip().lower()
    if configured in {"runpod", "service", "local"}:
        return configured
    if _runpod_enabled():
        return "runpod"
    if _service_base_url():
        return "service"
    return "local"


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


def _post_json(path: str, payload: dict) -> dict | None:
    base_url = _service_base_url()
    if not base_url:
        return None

    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=f"{base_url}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=_service_timeout()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Falling back to local AI facade after remote call failure: %s", exc)
        return None


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
            return {
                "status": status,
                "mode": "runpod",
                "message": (
                    payload.get("cuda", {}).get("device")
                    or payload.get("error")
                    or payload.get("message")
                    or "runpod"
                ),
            }
        return {
            "status": "offline",
            "mode": "runpod",
            "message": "RunPod health check failed.",
        }

    if provider == "service":
        remote = _post_json("/internal/health", {})
        if remote:
            return {
                "status": remote.get("status", "ok"),
                "mode": "service",
                "message": remote.get("role", "ai-microservice"),
            }
        return {
            "status": "offline",
            "mode": "service",
            "message": "Configured AI service is unavailable.",
        }

    return {
        "status": "fallback",
        "mode": "local",
        "message": "Local AI fallback is active.",
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
    preference = _build_preference_payload(survey_data)
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
                "recommended_style": result.get("recommended_style"),
            }
            enriched["reasoning_snapshot"] = snapshot
        augmented.append(enriched)
    return augmented


def simulate_face_analysis(*, image_url: str | None = None, image_bytes: bytes | None = None) -> dict:
    payload = {"image_url": image_url}
    if image_bytes is not None:
        payload["image_base64"] = base64.b64encode(image_bytes).decode("ascii")
    remote = _post_json("/internal/analyze-face", payload)
    if remote:
        return remote
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
    if _ai_provider() == "service":
        remote = _post_json(
            "/internal/generate-simulations",
            {
                "client_id": client_id,
                "survey_data": survey_data or {},
                "analysis_data": analysis_data,
                "scoring_weights": scoring_weights.as_dict(),
            },
        )
        if remote and isinstance(remote.get("items"), list):
            return remote["items"]

    survey = SimpleNamespace(client_id=client_id, **(survey_data or {}))
    analysis = SimpleNamespace(**analysis_data)
    items = score_recommendations(
        survey=survey,
        analysis=analysis,
        styles_by_id=styles_by_id,
        scoring_weights=scoring_weights,
    )
    return _augment_items_with_runpod(items=items, survey_data=survey_data, analysis_data=analysis_data)


def explain_style(*, card: dict) -> dict:
    remote = _post_json("/internal/explain-style", {"card": card})
    if remote:
        return remote
    return {
        "style_id": card.get("style_id"),
        "style_name": card.get("style_name"),
        "sample_image_url": card.get("sample_image_url"),
        "simulation_image_url": card.get("simulation_image_url"),
        "llm_explanation": card.get("llm_explanation"),
        "keywords": card.get("keywords", []),
    }
