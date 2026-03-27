import logging
import uuid
from types import SimpleNamespace

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from app.api.v1.recommendation_logic import (
    RETRY_SCORING_WEIGHTS,
    STYLE_CATALOG,
    build_preference_vector,
)
from app.models_django import (
    CaptureRecord,
    ConsultationRequest,
    Client,
    FaceAnalysis,
    FormerRecommendation,
    AdminAccount,
    Style,
    StyleSelection,
    Survey,
)
from app.services.age_profile import build_client_age_profile, client_matches_age_profile
from app.services.ai_facade import generate_recommendation_batch, simulate_face_analysis
from app.services.storage_service import resolve_storage_reference
from app.trend_pipeline.style_collection import load_hairstyles


logger = logging.getLogger(__name__)


REGENERATION_MAX_ATTEMPTS = 1
REGENERATION_POLICY = {
    "mode": "single_retry",
    "seed_strategy": "vary_seed",
    "selection_bias": "face_ratio_preference_boost",
    "trend_bias": "reduced",
}

RETRY_RECOMMENDATION_MAX_ATTEMPTS = 1
RETRY_RECOMMENDATION_POLICY = {
    "mode": "single_retry",
    "trend_included": False,
    "preference_weight": 70,
    "face_shape_weight": 20,
    "ratio_weight": 10,
    "face_total_weight": 30,
    "selection_bias": "preference_dominant",
}


def _seed_trend_styles(limit: int = 5) -> list[dict]:
    try:
        styles = load_hairstyles()
    except FileNotFoundError:
        return []
    return styles[:limit]


def build_default_survey_context(client_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        client_id=client_id,
        target_length=None,
        target_vibe=None,
        scalp_type=None,
        hair_colour=None,
        budget_range=None,
        preference_vector=[0.0] * 20,
    )


def ensure_catalog_styles() -> dict[int, Style]:
    styles_by_id: dict[int, Style] = {
        style.id: style
        for style in Style.objects.filter(id__in=[profile.style_id for profile in STYLE_CATALOG])
    }
    for profile in STYLE_CATALOG:
        if profile.style_id in styles_by_id:
            continue
        styles_by_id[profile.style_id] = Style.objects.create(
            id=profile.style_id,
            name=profile.fallback_name,
            vibe=(profile.vibe_tags[0] if profile.vibe_tags else "natural").title(),
            description=profile.fallback_description,
            image_url=profile.fallback_sample_image_url,
        )
    return styles_by_id


def _style_reference(style_id: int, *, styles_by_id: dict[int, Style] | None = None) -> dict:
    styles_by_id = styles_by_id or ensure_catalog_styles()
    style = styles_by_id.get(style_id) or Style.objects.filter(id=style_id).first()
    profile = next((item for item in STYLE_CATALOG if item.style_id == style_id), None)
    sample_image_url = None
    if style and style.image_url:
        sample_image_url = resolve_storage_reference(style.image_url)
    elif profile:
        sample_image_url = resolve_storage_reference(profile.fallback_sample_image_url)

    return {
        "sample_image_url": sample_image_url,
        "style_name": (style.name if style else (profile.fallback_name if profile else f"Style {style_id}")),
        "style_description": (style.description if style else (profile.fallback_description if profile else "")) or "",
        "keywords": list(profile.keywords) if profile else ([style.vibe] if style and style.vibe else []),
    }


def get_latest_survey(client: Client):
    return Survey.objects.filter(client=client).order_by("-created_at").first()


def get_latest_analysis(client: Client):
    return FaceAnalysis.objects.filter(client=client).order_by("-created_at").first()


def get_latest_capture(client: Client):
    return (
        CaptureRecord.objects.filter(client=client, status="DONE")
        .order_by("-created_at")
        .first()
    )


def get_latest_capture_attempt(client: Client):
    return CaptureRecord.objects.filter(client=client).order_by("-created_at").first()


def build_survey_snapshot(client: Client) -> dict | None:
    survey = get_latest_survey(client)
    if not survey:
        return None
    return {
        "target_length": survey.target_length,
        "target_vibe": survey.target_vibe,
        "scalp_type": survey.scalp_type,
        "hair_colour": survey.hair_colour,
        "budget_range": survey.budget_range,
        "preference_vector": survey.preference_vector or [],
        "age_profile": build_client_age_profile(client),
        "created_at": survey.created_at.isoformat(),
    }


def build_recommendation_regeneration_snapshot(
    *,
    client: Client,
    survey,
    analysis: FaceAnalysis | None,
    source: str,
    capture_record: CaptureRecord | None = None,
    recommendation_stage: str = "initial",
) -> dict:
    return {
        "version": "vector-only-v1",
        "source": source,
        "client_id": client.id,
        "recommendation_stage": recommendation_stage,
        "context": {
            "capture_record_id": (capture_record.id if capture_record else None),
            "survey_id": getattr(survey, "id", None),
            "analysis_id": (analysis.id if analysis else None),
        },
        "survey_data": {
            "target_length": getattr(survey, "target_length", None),
            "target_vibe": getattr(survey, "target_vibe", None),
            "scalp_type": getattr(survey, "scalp_type", None),
            "hair_colour": getattr(survey, "hair_colour", None),
            "budget_range": getattr(survey, "budget_range", None),
            "preference_vector": getattr(survey, "preference_vector", None) or [],
            "age_profile": build_client_age_profile(client),
        },
        "analysis_data": (
            {
                "face_shape": analysis.face_shape,
                "golden_ratio_score": analysis.golden_ratio_score,
                "landmark_snapshot": analysis.landmark_snapshot,
            }
            if analysis
            else None
        ),
    }


def upsert_survey(client: Client, payload: dict) -> Survey:
    preference_vector = build_preference_vector(
        target_length=payload.get("target_length"),
        target_vibe=payload.get("target_vibe"),
        scalp_type=payload.get("scalp_type"),
        hair_colour=payload.get("hair_colour"),
        budget_range=payload.get("budget_range"),
    )
    survey, _ = Survey.objects.update_or_create(
        client=client,
        defaults={
            "target_length": payload.get("target_length"),
            "target_vibe": payload.get("target_vibe"),
            "scalp_type": payload.get("scalp_type"),
            "hair_colour": payload.get("hair_colour"),
            "budget_range": payload.get("budget_range"),
            "preference_vector": preference_vector,
        },
    )
    return survey


def persist_generated_batch(
    *,
    client: Client,
    capture_record: CaptureRecord | None,
    survey,
    analysis: FaceAnalysis,
    recommendation_stage: str = "initial",
) -> tuple[str, list[FormerRecommendation]]:
    styles_by_id = ensure_catalog_styles()
    survey_payload = {
        "target_length": getattr(survey, "target_length", None),
        "target_vibe": getattr(survey, "target_vibe", None),
        "scalp_type": getattr(survey, "scalp_type", None),
        "hair_colour": getattr(survey, "hair_colour", None),
        "budget_range": getattr(survey, "budget_range", None),
    }
    items = generate_recommendation_batch(
        client_id=client.id,
        survey_data=survey_payload,
        analysis_data={
            "face_shape": analysis.face_shape,
            "golden_ratio_score": analysis.golden_ratio_score,
            "image_url": resolve_storage_reference(analysis.image_url),
            "landmark_snapshot": analysis.landmark_snapshot,
        },
        styles_by_id=styles_by_id,
        scoring_weights=(RETRY_SCORING_WEIGHTS if recommendation_stage == "retry" else None),
    )
    regeneration_snapshot = build_recommendation_regeneration_snapshot(
        client=client,
        survey=survey,
        analysis=analysis,
        source="generated",
        capture_record=capture_record,
        recommendation_stage=recommendation_stage,
    )

    batch_id = uuid.uuid4()
    rows: list[FormerRecommendation] = []
    for item in items:
        style = styles_by_id.get(item["style_id"])
        reasoning_snapshot = dict(item.get("reasoning_snapshot") or {})
        reasoning_snapshot["recommendation_stage"] = recommendation_stage
        rows.append(
            FormerRecommendation(
                client=client,
                capture_record=capture_record,
                style=style,
                batch_id=batch_id,
                source="generated",
                style_id_snapshot=item["style_id"],
                style_name_snapshot=item["style_name"],
                style_description_snapshot=item.get("style_description", ""),
                keywords=item.get("keywords", []),
                sample_image_url=None,
                simulation_image_url=None,
                regeneration_snapshot=regeneration_snapshot,
                llm_explanation=item.get("llm_explanation"),
                reasoning_snapshot=reasoning_snapshot,
                match_score=item.get("match_score"),
                rank=item.get("rank", 0),
            )
        )
    FormerRecommendation.objects.bulk_create(rows)
    return str(batch_id), list(FormerRecommendation.objects.filter(batch_id=batch_id).order_by("rank", "id"))


def serialize_recommendation_row(row: FormerRecommendation) -> dict:
    reasoning_snapshot = row.reasoning_snapshot or {}
    style_reference = _style_reference(
        row.style_id_snapshot,
        styles_by_id=({row.style_id_snapshot: row.style} if row.style else None),
    )
    uses_vector_only_policy = bool(row.regeneration_snapshot)
    regeneration_attempts_used = int(reasoning_snapshot.get("regeneration_attempts_used") or 0)
    regeneration_attempts_allowed = (
        REGENERATION_MAX_ATTEMPTS if uses_vector_only_policy else 0
    )
    regeneration_remaining_count = max(0, regeneration_attempts_allowed - regeneration_attempts_used)
    can_regenerate_simulation = uses_vector_only_policy and regeneration_remaining_count > 0
    sample_image_url = style_reference["sample_image_url"] or resolve_storage_reference(row.sample_image_url)
    simulation_image_url = None if uses_vector_only_policy else resolve_storage_reference(row.simulation_image_url)
    reference_images = []
    if sample_image_url:
        reference_images.append(
            {
                "image_url": sample_image_url,
                "description": row.style_description_snapshot or style_reference["style_description"],
            }
        )
    return {
        "recommendation_id": row.id,
        "batch_id": row.batch_id,
        "source": row.source,
        "style_id": row.style_id_snapshot,
        "style_name": row.style_name_snapshot or style_reference["style_name"],
        "style_description": row.style_description_snapshot or style_reference["style_description"],
        "keywords": row.keywords or style_reference["keywords"],
        "sample_image_url": sample_image_url,
        "reference_images": reference_images,
        "simulation_image_url": simulation_image_url,
        "synthetic_image_url": simulation_image_url,
        "llm_explanation": row.llm_explanation or "",
        "reasoning": reasoning_snapshot.get("summary") or row.llm_explanation or "",
        "reasoning_snapshot": reasoning_snapshot,
        "match_score": row.match_score or 0.0,
        "rank": row.rank,
        "is_chosen": row.is_chosen,
        "image_policy": ("vector_only" if uses_vector_only_policy else "legacy_asset_store"),
        "can_regenerate_simulation": can_regenerate_simulation,
        "regeneration_remaining_count": regeneration_remaining_count,
        "regeneration_policy": (
            {
                **REGENERATION_POLICY,
                "attempts_allowed": regeneration_attempts_allowed,
                "attempts_used": regeneration_attempts_used,
            }
            if uses_vector_only_policy
            else None
        ),
        "created_at": row.created_at,
    }


def _serialize_row(row: FormerRecommendation) -> dict:
    return serialize_recommendation_row(row)


def _get_recommendation_stage(rows: list[FormerRecommendation]) -> str:
    if not rows:
        return "initial"
    snapshot = rows[0].reasoning_snapshot or {}
    return str(snapshot.get("recommendation_stage") or "initial")


def _build_retry_recommendation_meta(*, rows: list[FormerRecommendation], has_active_consultation: bool) -> dict:
    recommendation_stage = _get_recommendation_stage(rows)
    attempts_used = 1 if recommendation_stage == "retry" else 0
    can_retry = bool(rows) and recommendation_stage == "initial" and not has_active_consultation
    remaining_count = max(0, RETRY_RECOMMENDATION_MAX_ATTEMPTS - attempts_used) if can_retry else 0
    return {
        "recommendation_stage": recommendation_stage,
        "can_retry_recommendations": can_retry,
        "retry_recommendations_remaining_count": remaining_count,
        "retry_recommendations_policy": {
            **RETRY_RECOMMENDATION_POLICY,
            "attempts_allowed": RETRY_RECOMMENDATION_MAX_ATTEMPTS,
            "attempts_used": attempts_used,
        },
    }


def _scoring_weights_for_stage(recommendation_stage: str):
    if recommendation_stage == "retry":
        return RETRY_SCORING_WEIGHTS
    return None


def _build_empty_response(*, source: str, message: str, next_action: str | None = None, next_actions: list[str] | None = None) -> dict:
    payload = {
        "status": "empty",
        "source": source,
        "message": message,
        "items": [],
    }
    if next_action:
        payload["next_action"] = next_action
    if next_actions:
        payload["next_actions"] = next_actions
    return payload


def serialize_capture_status(record: CaptureRecord) -> dict:
    privacy_snapshot = record.privacy_snapshot or {}
    payload = {
        "record_id": record.id,
        "status": record.status.lower(),
        "face_count": record.face_count,
        "error_note": record.error_note,
        "landmark_snapshot": record.landmark_snapshot,
        "deidentified_image_url": resolve_storage_reference(record.deidentified_path),
        "privacy_snapshot": privacy_snapshot,
        "image_storage_policy": privacy_snapshot.get("storage_policy", "asset_store"),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }
    if record.status in {"NEEDS_RETAKE", "FAILED"}:
        payload["next_action"] = "capture"
    return payload


def regenerate_recommendation_simulation(
    *,
    recommendation_id: int | None = None,
    regeneration_snapshot: dict | None = None,
    style_id: int | None = None,
) -> dict:
    selected_row = None
    if recommendation_id is not None:
        selected_row = FormerRecommendation.objects.filter(id=recommendation_id).first()
        if not selected_row:
            raise ValueError("The selected recommendation could not be found.")
        regeneration_snapshot = regeneration_snapshot or selected_row.regeneration_snapshot
        style_id = style_id or selected_row.style_id_snapshot
        attempts_used = int((selected_row.reasoning_snapshot or {}).get("regeneration_attempts_used") or 0)
        if attempts_used >= REGENERATION_MAX_ATTEMPTS:
            raise ValueError("This recommendation has already used its one allowed regeneration.")

    if not regeneration_snapshot:
        raise ValueError("No regeneration snapshot is available for this recommendation.")
    if style_id is None:
        raise ValueError("Style information is required to regenerate the simulation.")

    survey_data = dict(regeneration_snapshot.get("survey_data") or {})
    analysis_data = dict(regeneration_snapshot.get("analysis_data") or {})
    client_id = int(regeneration_snapshot.get("client_id") or 0)
    recommendation_stage = str(regeneration_snapshot.get("recommendation_stage") or "initial")
    if client_id <= 0:
        raise ValueError("The regeneration snapshot is missing client context.")

    styles_by_id = ensure_catalog_styles()
    generated_items = generate_recommendation_batch(
        client_id=client_id,
        survey_data=survey_data,
        analysis_data=analysis_data,
        styles_by_id=styles_by_id,
        scoring_weights=_scoring_weights_for_stage(recommendation_stage),
    )
    regenerated_card = next(
        (item for item in generated_items if int(item.get("style_id", -1)) == int(style_id)),
        None,
    )
    if regenerated_card is None:
        raise ValueError("Could not regenerate the requested style from the current snapshot.")

    if selected_row is not None:
        reasoning_snapshot = dict(selected_row.reasoning_snapshot or {})
        attempts_used = int(reasoning_snapshot.get("regeneration_attempts_used") or 0) + 1
        reasoning_snapshot["regenerated"] = True
        reasoning_snapshot["regeneration_source"] = regeneration_snapshot.get("source")
        reasoning_snapshot["regeneration_attempts_used"] = attempts_used
        reasoning_snapshot["regeneration_attempts_allowed"] = REGENERATION_MAX_ATTEMPTS
        reasoning_snapshot["regeneration_remaining_count"] = max(0, REGENERATION_MAX_ATTEMPTS - attempts_used)
        reasoning_snapshot["regeneration_policy"] = dict(REGENERATION_POLICY)

        selected_row.reasoning_snapshot = reasoning_snapshot
        selected_row.match_score = regenerated_card.get("match_score") or selected_row.match_score
        selected_row.llm_explanation = regenerated_card.get("llm_explanation") or selected_row.llm_explanation
        selected_row.save(update_fields=["reasoning_snapshot", "match_score", "llm_explanation"])
        card = serialize_recommendation_row(selected_row)
    else:
        style_reference = _style_reference(int(style_id), styles_by_id=styles_by_id)
        card = {
            "recommendation_id": None,
            "batch_id": None,
            "source": "generated",
            "style_id": int(style_id),
            "style_name": regenerated_card.get("style_name") or style_reference["style_name"],
            "style_description": regenerated_card.get("style_description") or style_reference["style_description"],
            "keywords": regenerated_card.get("keywords") or style_reference["keywords"],
            "sample_image_url": regenerated_card.get("sample_image_url") or style_reference["sample_image_url"],
            "reference_images": [],
            "simulation_image_url": None,
            "synthetic_image_url": None,
            "llm_explanation": regenerated_card.get("llm_explanation") or "",
            "reasoning": regenerated_card.get("reasoning") or "",
            "reasoning_snapshot": {
                **(regenerated_card.get("reasoning_snapshot") or {}),
                "regenerated": True,
                "regeneration_source": regeneration_snapshot.get("source"),
                "regeneration_attempts_used": 1,
                "regeneration_attempts_allowed": REGENERATION_MAX_ATTEMPTS,
                "regeneration_remaining_count": 0,
                "regeneration_policy": dict(REGENERATION_POLICY),
            },
            "image_policy": "vector_only",
            "can_regenerate_simulation": False,
            "regeneration_remaining_count": 0,
            "regeneration_policy": {
                **REGENERATION_POLICY,
                "attempts_allowed": REGENERATION_MAX_ATTEMPTS,
                "attempts_used": 1,
            },
            "match_score": regenerated_card.get("match_score") or 0.0,
            "rank": regenerated_card.get("rank") or 1,
            "is_chosen": False,
            "created_at": timezone.now(),
        }

    card["simulation_image_url"] = regenerated_card.get("simulation_image_url")
    card["synthetic_image_url"] = regenerated_card.get("synthetic_image_url")
    card["image_policy"] = "vector_only"
    card["can_regenerate_simulation"] = False
    card["regeneration_remaining_count"] = 0
    card["reasoning"] = regenerated_card.get("reasoning") or card.get("reasoning") or ""
    card["llm_explanation"] = regenerated_card.get("llm_explanation") or card.get("llm_explanation") or ""

    return {
        "status": "success",
        "recommendation_id": (selected_row.id if selected_row else None),
        "style_id": int(style_id),
        "image_policy": "vector_only",
        "can_regenerate_simulation": False,
        "regeneration_remaining_count": 0,
        "regeneration_policy": {
            **REGENERATION_POLICY,
            "attempts_allowed": REGENERATION_MAX_ATTEMPTS,
            "attempts_used": 1,
        },
        "simulation_image_url": card.get("simulation_image_url"),
        "synthetic_image_url": card.get("synthetic_image_url"),
        "card": card,
        "message": "A regenerated simulation payload is ready.",
    }


def get_former_recommendations(client: Client) -> dict:
    latest_generated = (
        FormerRecommendation.objects.filter(client=client, source="generated")
        .order_by("-created_at")
        .first()
    )
    queryset = FormerRecommendation.objects.filter(client=client)
    if latest_generated:
        latest_batch_has_choice = queryset.filter(batch_id=latest_generated.batch_id, is_chosen=True).exists()
        if not latest_batch_has_choice:
            queryset = queryset.exclude(batch_id=latest_generated.batch_id)

    rows = list(queryset.order_by("-is_chosen", "-chosen_at", "-created_at")[:5])
    if not rows:
        return _build_empty_response(
            source="former_recommendations",
            message="No previous recommendation history is available yet. Start with trend cards or upload a new capture.",
            next_actions=["trend", "capture"],
        )

    return {
        "status": "ready",
        "source": "former_recommendations",
        "items": [_serialize_row(row) for row in rows],
    }


def _ensure_current_batch(client: Client) -> tuple[str | None, list[FormerRecommendation], str | None]:
    latest_analysis = get_latest_analysis(client)
    latest_capture = get_latest_capture(client)
    latest_survey = get_latest_survey(client)
    latest_batch = (
        FormerRecommendation.objects.filter(client=client, source="generated")
        .order_by("-created_at")
        .first()
    )

    if not latest_capture or not latest_analysis:
        return None, [], "needs_capture"

    needs_regeneration = latest_batch is None
    if latest_batch and latest_capture and latest_batch.created_at < latest_capture.created_at:
        needs_regeneration = True
    if latest_batch and latest_analysis and latest_batch.created_at < latest_analysis.created_at:
        needs_regeneration = True
    if latest_batch and latest_survey and latest_batch.created_at < latest_survey.created_at:
        needs_regeneration = True

    if needs_regeneration:
        survey_context = latest_survey or build_default_survey_context(client.id)
        _, rows = persist_generated_batch(
            client=client,
            capture_record=latest_capture,
            survey=survey_context,
            analysis=latest_analysis,
        )
        return (str(rows[0].batch_id) if rows else None), rows, None

    rows = list(
        FormerRecommendation.objects.filter(client=client, batch_id=latest_batch.batch_id).order_by("rank", "id")
    )
    return str(latest_batch.batch_id), rows, None


def get_current_recommendations(client: Client) -> dict:
    latest_capture_attempt = get_latest_capture_attempt(client)
    latest_survey = get_latest_survey(client)
    latest_capture = get_latest_capture(client)
    latest_analysis = get_latest_analysis(client)

    if (
        latest_capture is None
        and latest_capture_attempt is not None
        and latest_capture_attempt.status in {"NEEDS_RETAKE", "FAILED"}
    ):
        return {
            "status": "needs_capture",
            "source": "current_recommendations",
            "message": latest_capture_attempt.error_note or "Face detection did not succeed. Please retake a front-facing photo.",
            "next_action": "capture",
            "items": [],
        }

    if not latest_capture and not latest_survey:
        return {
            "status": "needs_input",
            "source": "current_recommendations",
            "message": "No survey or capture data is available yet. Start with the survey or upload a capture.",
            "next_actions": ["survey", "capture"],
            "items": [],
        }

    if not latest_capture or not latest_analysis:
        return {
            "status": "needs_capture",
            "source": "current_recommendations",
            "message": "A valid front-facing capture is required before we can generate the current Top-5 recommendations.",
            "next_action": "capture",
            "items": [],
        }

    batch_id, rows, status_code = _ensure_current_batch(client)
    if status_code == "needs_capture":
        return {
            "status": "needs_capture",
            "source": "current_recommendations",
            "message": "Capture data is not ready yet. Please complete capture before requesting current recommendations.",
            "next_action": "capture",
            "items": [],
        }

    if not rows:
        return _build_empty_response(
            source="current_recommendations",
            message="No recommendation batch is available yet. Please retake the capture and try again.",
            next_action="capture",
        )

    has_active_consultation = ConsultationRequest.objects.filter(client=client, is_active=True).exists()
    retry_meta = _build_retry_recommendation_meta(
        rows=rows,
        has_active_consultation=has_active_consultation,
    )
    message = "The latest Top-5 recommendations were generated from the most recent capture and analysis."
    if latest_survey is None:
        message = "The latest Top-5 recommendations were generated from face analysis only because survey data is not available."
    elif retry_meta["recommendation_stage"] == "retry":
        message = "The recommendations were regenerated once with preference-first scoring and no trend influence."

    payload = {
        "status": "ready",
        "source": "current_recommendations",
        "batch_id": batch_id,
        "message": message,
        "items": [_serialize_row(row) for row in rows],
    }
    payload.update(retry_meta)
    payload["next_actions"] = (
        ["retry_recommendations", "consultation"]
        if retry_meta["can_retry_recommendations"]
        else ["consultation"]
    )
    return payload


def retry_current_recommendations(client: Client) -> dict:
    latest_capture = get_latest_capture(client)
    latest_analysis = get_latest_analysis(client)
    latest_survey = get_latest_survey(client)
    if not latest_capture or not latest_analysis:
        raise ValueError("A completed capture and face analysis are required before retrying recommendations.")

    latest_batch = (
        FormerRecommendation.objects.filter(client=client, source="generated")
        .order_by("-created_at")
        .first()
    )
    if latest_batch is None:
        raise ValueError("Retry is available only after the initial recommendation batch has been generated.")
    if latest_batch.created_at < latest_capture.created_at or latest_batch.created_at < latest_analysis.created_at:
        raise ValueError("Retry is available only for the latest initial recommendation batch. Refresh current recommendations first.")
    if latest_survey is not None and latest_batch.created_at < latest_survey.created_at:
        raise ValueError("Retry is available only for the latest initial recommendation batch. Refresh current recommendations first.")

    rows = list(
        FormerRecommendation.objects.filter(client=client, batch_id=latest_batch.batch_id).order_by("rank", "id")
    )
    if not rows:
        raise ValueError("Initial recommendations must be ready before retry is available.")

    if ConsultationRequest.objects.filter(client=client, is_active=True).exists():
        raise ValueError("Retry is not available after the consultation flow has started.")

    current_stage = _get_recommendation_stage(rows)
    if current_stage != "initial":
        raise ValueError("Retry recommendations are only available once after the initial recommendation batch.")

    if any(row.is_chosen for row in rows):
        raise ValueError("Retry is not available after a recommendation has already been selected.")

    survey_context = latest_survey or build_default_survey_context(client.id)
    new_batch_id, new_rows = persist_generated_batch(
        client=client,
        capture_record=latest_capture,
        survey=survey_context,
        analysis=latest_analysis,
        recommendation_stage="retry",
    )
    retry_meta = _build_retry_recommendation_meta(
        rows=new_rows,
        has_active_consultation=False,
    )
    return {
        "status": "ready",
        "source": "current_recommendations",
        "batch_id": new_batch_id,
        "message": "A one-time retry recommendation batch has been generated with preference-first scoring.",
        "items": [_serialize_row(row) for row in new_rows],
        "next_actions": ["consultation"],
        **retry_meta,
    }


def get_trend_recommendations(*, days: int = 30, client: Client | None = None) -> dict:
    cutoff = timezone.now() - timezone.timedelta(days=days)
    target_age_profile = build_client_age_profile(client) if client else None
    selections = list(
        StyleSelection.objects.filter(created_at__gte=cutoff).select_related("client").order_by("-created_at")
    )
    scoped_selections = selections
    trend_scope = "global"
    if target_age_profile:
        exact_group_matches = [
            row
            for row in selections
            if client_matches_age_profile(row.client, age_group=target_age_profile["age_group"])
        ]
        decade_matches = [
            row
            for row in selections
            if client_matches_age_profile(row.client, age_decade=target_age_profile["age_decade"])
        ]
        if exact_group_matches:
            scoped_selections = exact_group_matches
            trend_scope = "age_group"
        elif decade_matches:
            scoped_selections = decade_matches
            trend_scope = "age_decade"

    popular_style_ids = []
    if scoped_selections:
        popular_style_ids = (
            StyleSelection.objects.filter(id__in=[row.id for row in scoped_selections])
            .values("style_id")
            .annotate(selection_count=Count("id"))
            .order_by("-selection_count", "style_id")[:5]
        )

    items: list[dict] = []
    for rank, item in enumerate(popular_style_ids, start=1):
        style = Style.objects.filter(id=item["style_id"]).first()
        if not style:
            continue
        trend_summary = f"recent confirmed selections in the last {days} days"
        if trend_scope == "age_group" and target_age_profile:
            trend_summary = f"{target_age_profile['age_group']} selections in the last {days} days"
        elif trend_scope == "age_decade" and target_age_profile:
            trend_summary = f"{target_age_profile['age_decade']} selections in the last {days} days"
        items.append(
            {
                "source": "trend",
                "style_id": style.id,
                "style_name": style.name,
                "style_description": style.description or f"This style has been selected frequently in the last {days} days.",
                "keywords": [style.vibe] if style.vibe else [],
                "sample_image_url": resolve_storage_reference(style.image_url),
                "simulation_image_url": resolve_storage_reference(style.image_url),
                "synthetic_image_url": resolve_storage_reference(style.image_url),
                "llm_explanation": style.description or f"This style has been selected frequently in the last {days} days.",
                "reasoning": f"Sorted by confirmed selection count over the last {days} days.",
                "reasoning_snapshot": {
                    "summary": trend_summary,
                    "selection_count": int(item["selection_count"]),
                    "days": days,
                    "source": "trend",
                    "trend_scope": trend_scope,
                    "age_profile": target_age_profile,
                },
                "match_score": float(item["selection_count"]),
                "rank": rank,
                "is_chosen": False,
            }
        )

    if not items:
        seed_styles = _seed_trend_styles(limit=5)
        seeded_names = [str(item.get("style_name") or "").strip() for item in seed_styles if str(item.get("style_name") or "").strip()]
        db_seeded = {style.name: style for style in Style.objects.filter(name__in=seeded_names)}

        for rank, seed in enumerate(seed_styles, start=1):
            style = db_seeded.get(str(seed.get("style_name") or "").strip())
            if not style:
                continue
            items.append(
                {
                    "source": "trend",
                    "style_id": style.id,
                    "style_name": style.name,
                    "style_description": style.description or str(seed.get("description") or ""),
                    "keywords": list(seed.get("keywords") or ([style.vibe] if style.vibe else [])),
                    "sample_image_url": resolve_storage_reference(style.image_url),
                    "simulation_image_url": resolve_storage_reference(style.image_url),
                    "synthetic_image_url": resolve_storage_reference(style.image_url),
                    "llm_explanation": style.description or str(seed.get("description") or ""),
                    "reasoning": "fallback trend catalog synced from refreshed seed data",
                    "reasoning_snapshot": {
                        "summary": "fallback trend catalog synced from refreshed seed data",
                        "selection_count": 0,
                        "days": days,
                        "source": "trend",
                        "trend_scope": trend_scope,
                        "age_profile": target_age_profile,
                        "seed_source": str(seed.get("source") or ""),
                        "seed_last_updated": str(seed.get("last_updated") or ""),
                    },
                    "match_score": float(seed.get("freshness_score") or 0.0),
                    "rank": rank,
                    "is_chosen": False,
                }
            )

    if not items:
        styles_by_id = ensure_catalog_styles()
        fallback_ids = [201, 203, 205, 204, 207]
        for rank, style_id in enumerate(fallback_ids, start=1):
            style = styles_by_id[style_id]
            items.append(
                {
                    "source": "trend",
                    "style_id": style.id,
                    "style_name": style.name,
                    "style_description": style.description or "",
                    "keywords": [style.vibe] if style.vibe else [],
                    "sample_image_url": resolve_storage_reference(style.image_url),
                    "simulation_image_url": resolve_storage_reference(style.image_url),
                    "synthetic_image_url": resolve_storage_reference(style.image_url),
                    "llm_explanation": "Recent confirmed-selection data is limited, so the default trend catalog is shown.",
                    "reasoning": "fallback trend catalog",
                    "reasoning_snapshot": {
                        "summary": "fallback trend catalog",
                        "selection_count": 0,
                        "days": days,
                        "source": "trend",
                        "trend_scope": trend_scope,
                        "age_profile": target_age_profile,
                    },
                    "match_score": 0.0,
                    "rank": rank,
                    "is_chosen": False,
                }
            )

    return {
        "status": "ready",
        "source": "trend",
        "days": days,
        "trend_scope": trend_scope,
        "age_profile": target_age_profile,
        "items": items,
    }


def confirm_style_selection(
    *,
    client: Client,
    recommendation_id: int | None = None,
    style_id: int | None = None,
    admin_id: int | None = None,
    source: str = "current_recommendations",
    direct_consultation: bool = False,
) -> dict:
    latest_analysis = get_latest_analysis(client)
    survey_snapshot = build_survey_snapshot(client)
    analysis_snapshot = {}
    if latest_analysis:
        analysis_snapshot = {
            "face_shape": latest_analysis.face_shape,
            "golden_ratio": latest_analysis.golden_ratio_score,
            "image_url": resolve_storage_reference(latest_analysis.image_url),
            "landmark_snapshot": latest_analysis.landmark_snapshot,
        }

    selected_style = None
    selected_row = None
    admin = AdminAccount.objects.filter(id=admin_id).first() if admin_id else None
    if recommendation_id is not None:
        selected_row = FormerRecommendation.objects.filter(id=recommendation_id, client=client).first()
        if not selected_row:
            raise ValueError("The selected recommendation could not be found.")

        FormerRecommendation.objects.filter(client=client, batch_id=selected_row.batch_id).update(
            is_chosen=False,
            chosen_at=None,
        )
        selected_row.is_chosen = True
        selected_row.chosen_at = timezone.now()
        selected_row.is_sent_to_admin = True
        selected_row.sent_at = timezone.now()
        selected_row.save(update_fields=["is_chosen", "chosen_at", "is_sent_to_admin", "sent_at"])
        style_id = selected_row.style_id_snapshot
        selected_style = selected_row.style or Style.objects.filter(id=style_id).first()

    if selected_style is None and style_id is not None:
        selected_style = Style.objects.filter(id=style_id).first()

    if recommendation_id is None and selected_style is not None and source == "current_recommendations":
        selected_row = (
            FormerRecommendation.objects.filter(
                client=client,
                source="generated",
                style_id_snapshot=selected_style.id,
            )
            .order_by("-created_at")
            .first()
        )
        if selected_row:
            FormerRecommendation.objects.filter(client=client, batch_id=selected_row.batch_id).update(
                is_chosen=False,
                chosen_at=None,
            )
            selected_row.is_chosen = True
            selected_row.chosen_at = timezone.now()
            selected_row.is_sent_to_admin = True
            selected_row.sent_at = timezone.now()
            selected_row.save(update_fields=["is_chosen", "chosen_at", "is_sent_to_admin", "sent_at"])

    if not direct_consultation and selected_style is None:
        raise ValueError("Style information is required to confirm a selection.")

    if recommendation_id is None and selected_style is not None and source == "trend":
        explanation = selected_style.description or "This style was selected from the current salon trend list."
        regeneration_snapshot = build_recommendation_regeneration_snapshot(
            client=client,
            survey=(get_latest_survey(client) or build_default_survey_context(client.id)),
            analysis=latest_analysis,
            source="trend",
        )
        selected_row = FormerRecommendation.objects.create(
            client=client,
            style=selected_style,
            batch_id=uuid.uuid4(),
            source="trend",
            style_id_snapshot=selected_style.id,
            style_name_snapshot=selected_style.name,
            style_description_snapshot=selected_style.description or "",
            keywords=[selected_style.vibe] if selected_style.vibe else [],
            sample_image_url=None,
            simulation_image_url=None,
            regeneration_snapshot=regeneration_snapshot,
            llm_explanation=explanation,
            reasoning_snapshot={
                "summary": "trend selection promoted to consultation",
                "source": "trend",
            },
            match_score=None,
            rank=1,
            is_chosen=not direct_consultation,
            chosen_at=(timezone.now() if not direct_consultation else None),
            is_sent_to_admin=True,
            sent_at=timezone.now(),
        )

    if not direct_consultation and selected_style is not None:
        StyleSelection.objects.create(
            client=client,
            selected_recommendation=selected_row,
            style_id=selected_style.id,
            source=source,
            survey_snapshot=survey_snapshot,
            match_score=(selected_row.match_score if selected_row else None),
            is_sent_to_admin=True,
        )

    ConsultationRequest.objects.filter(client=client, is_active=True).update(
        is_active=False,
        status="CLOSED",
        closed_at=timezone.now(),
        is_read=True,
    )

    consultation = ConsultationRequest.objects.create(
        client=client,
        selected_style=(None if direct_consultation else selected_style),
        selected_recommendation=selected_row,
        admin=admin,
        source=source,
        survey_snapshot=survey_snapshot,
        analysis_data_snapshot=analysis_snapshot,
        status="PENDING",
        is_active=True,
        is_read=False,
    )

    return {
        "status": "success",
        "consultation_id": consultation.id,
        "selected_style_id": (selected_style.id if selected_style else None),
        "selected_style_name": (selected_style.name if selected_style else None),
        "source": source,
        "direct_consultation": direct_consultation,
        "recommendation_id": (selected_row.id if selected_row else None),
        "message": (
            "A direct consultation request has been sent to the admin."
            if direct_consultation
            else "The selected style and analysis summary have been handed off to the admin."
        ),
    }


def _resolve_cancellable_recommendation(
    *,
    client: Client,
    recommendation_id: int | None = None,
) -> FormerRecommendation | None:
    if recommendation_id is not None:
        selected_row = FormerRecommendation.objects.filter(id=recommendation_id, client=client).first()
        if not selected_row:
            raise ValueError("The recommendation to cancel could not be found.")
        return selected_row

    active_consultation = (
        ConsultationRequest.objects.filter(client=client, is_active=True)
        .select_related("selected_recommendation")
        .order_by("-created_at")
        .first()
    )
    if active_consultation and active_consultation.selected_recommendation_id:
        return active_consultation.selected_recommendation

    return (
        FormerRecommendation.objects.filter(client=client, is_chosen=True)
        .order_by("-chosen_at", "-created_at")
        .first()
    )


def cancel_style_selection(
    *,
    client: Client,
    recommendation_id: int | None = None,
    source: str = "current_recommendations",
) -> dict:
    cancelled_at = timezone.now()
    selected_row = _resolve_cancellable_recommendation(
        client=client,
        recommendation_id=recommendation_id,
    )

    with transaction.atomic():
        ConsultationRequest.objects.filter(client=client, is_active=True).update(
            is_active=False,
            status="CANCELLED",
            closed_at=cancelled_at,
            is_read=True,
        )

        if selected_row is not None:
            FormerRecommendation.objects.filter(client=client, batch_id=selected_row.batch_id).update(
                is_chosen=False,
                chosen_at=None,
                is_sent_to_admin=False,
                sent_at=None,
            )

    return {
        "status": "cancelled",
        "client_id": client.id,
        "source": source,
        "next_action": "client_input",
        "message": "The selected style has been cancelled and the flow can return to the client input step.",
    }


def run_mirrai_analysis_pipeline(record_id: int, processed_bytes: bytes | None = None):
    try:
        with transaction.atomic():
            record = CaptureRecord.objects.select_for_update().get(id=record_id)
            if record.status != "PENDING":
                return

            record.status = "PROCESSING"
            record.save(update_fields=["status", "updated_at"])

        analysis_input_url = resolve_storage_reference(record.processed_path)
        simulated = simulate_face_analysis(
            image_url=analysis_input_url,
            image_bytes=(processed_bytes if record.processed_path is None else None),
        )
        analysis = FaceAnalysis.objects.create(
            client=record.client,
            face_shape=simulated["face_shape"],
            golden_ratio_score=simulated["golden_ratio_score"],
            image_url=record.processed_path,
            landmark_snapshot=record.landmark_snapshot or simulated.get("landmark_snapshot"),
        )

        survey = get_latest_survey(record.client) or build_default_survey_context(record.client_id)
        persist_generated_batch(client=record.client, capture_record=record, survey=survey, analysis=analysis)

        record.status = "DONE"
        record.save(update_fields=["status", "updated_at"])
        logger.info("[PIPELINE SUCCESS] Record %s processed.", record_id)

    except Exception as exc:
        logger.error("[PIPELINE ERROR] Record %s: %s", record_id, exc)
        CaptureRecord.objects.filter(id=record_id).update(status="FAILED", error_note=str(exc))

