import logging
import uuid
from collections import Counter
from types import SimpleNamespace
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Count, Max, Q
from django.utils import timezone

from app.api.v1.recommendation_logic import (
    RETRY_SCORING_WEIGHTS,
    STYLE_CATALOG,
    build_preference_vector,
)
from app.models_model_team import (
    LegacyClientResult,
    LegacyClientResultDetail,
    LegacyHairstyle,
    LegacyClientSurvey,
)
from app.services.age_profile import build_client_age_profile, client_matches_age_profile
from app.services.ai_facade import generate_recommendation_batch, simulate_face_analysis
from app.services.model_team_bridge import (
    LEGACY_ANALYSIS_MODEL_COLUMNS,
    LEGACY_HAIRSTYLE_MODEL_COLUMNS,
    LEGACY_RESULT_DETAIL_MODEL_COLUMNS,
    LEGACY_RESULT_MODEL_COLUMNS,
    LEGACY_SURVEY_MODEL_COLUMNS,
    _has_columns,
    complete_legacy_capture_analysis,
    fail_legacy_capture_processing,
    find_legacy_recommendation_context,
    get_admin_by_identifier,
    get_legacy_active_consultation_items,
    get_legacy_client_id,
    get_legacy_confirmed_selection_items,
    get_style_record,
    get_style_record_by_name,
    get_latest_legacy_analysis,
    get_latest_legacy_capture,
    get_latest_legacy_survey,
    get_legacy_former_recommendation_items,
    has_legacy_analysis_source,
    has_legacy_result_source,
    mark_legacy_capture_processing,
    sync_model_team_rows,
    sync_model_team_runtime_state,
)
from app.services.storage_service import build_storage_snapshot, resolve_storage_reference
from app.trend_pipeline.style_collection import load_hairstyles

if TYPE_CHECKING:
    from app.models_django import (
        AdminAccount,
        CaptureRecord,
        ConsultationRequest,
        Client,
        FaceAnalysis,
        FormerRecommendation,
        Style,
        StyleSelection,
        Survey,
    )


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


def ensure_catalog_styles() -> dict[int, object]:
    styles_by_id: dict[int, object] = {
        profile.style_id: get_style_record(style_id=profile.style_id)
        for profile in STYLE_CATALOG
        if get_style_record(style_id=profile.style_id) is not None
    }
    for profile in STYLE_CATALOG:
        if profile.style_id in styles_by_id:
            continue
        style_defaults = {
            "chroma_id": str(profile.style_id),
            "style_name": profile.fallback_name,
            "image_url": profile.fallback_sample_image_url,
            "created_at": timezone.now().isoformat(),
            "backend_style_id": profile.style_id,
            "name": profile.fallback_name,
            "vibe": (profile.vibe_tags[0] if profile.vibe_tags else "natural").title(),
            "description": profile.fallback_description,
        }
        if _has_columns("hairstyle", LEGACY_HAIRSTYLE_MODEL_COLUMNS):
            LegacyHairstyle.objects.update_or_create(
                hairstyle_id=profile.style_id,
                defaults=style_defaults,
            )
            styles_by_id[profile.style_id] = get_style_record(style_id=profile.style_id)
            continue
        styles_by_id[profile.style_id] = SimpleNamespace(
            hairstyle_id=profile.style_id,
            backend_style_id=profile.style_id,
            name=profile.fallback_name,
            style_name=profile.fallback_name,
            vibe=style_defaults["vibe"],
            description=profile.fallback_description,
            image_url=profile.fallback_sample_image_url,
        )
    return styles_by_id


def _style_reference(style_id: int, *, styles_by_id: "dict[int, Style] | None" = None) -> dict:
    styles_by_id = styles_by_id or ensure_catalog_styles()
    style = styles_by_id.get(style_id) or get_style_record(style_id=style_id)
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


def get_latest_survey(client: "Client"):
    legacy_survey = get_latest_legacy_survey(client=client)
    if legacy_survey is not None:
        return legacy_survey
    return None


def get_latest_analysis(client: "Client"):
    legacy_analysis = get_latest_legacy_analysis(client=client)
    if legacy_analysis is not None:
        return legacy_analysis
    return None


def get_latest_capture(client: "Client"):
    legacy_capture = get_latest_legacy_capture(client=client)
    if legacy_capture is not None:
        return legacy_capture
    return None


def _legacy_survey_writable() -> bool:
    return _has_columns("client_survey", LEGACY_SURVEY_MODEL_COLUMNS)


def _legacy_result_writable() -> bool:
    return (
        _has_columns("client_result", LEGACY_RESULT_MODEL_COLUMNS)
        and _has_columns("client_result_detail", LEGACY_RESULT_DETAIL_MODEL_COLUMNS)
    )


def _next_legacy_pk(model, field_name: str) -> int:
    latest = model.objects.aggregate(max_value=Max(field_name)).get("max_value")
    return int(latest or 0) + 1


def _legacy_survey_namespace(*, survey_id: int, client: "Client", normalized_payload: dict, preference_vector: list[float], created_at) -> SimpleNamespace:
    return SimpleNamespace(
        id=survey_id,
        client=client.id,
        client_id=client.id,
        target_length=normalized_payload.get("target_length"),
        target_vibe=normalized_payload.get("target_vibe"),
        scalp_type=normalized_payload.get("scalp_type"),
        hair_colour=normalized_payload.get("hair_colour"),
        budget_range=normalized_payload.get("budget_range"),
        preference_vector=preference_vector,
        created_at=created_at,
    )


def _legacy_preference_vector_storage(preference_vector: list[float]) -> str:
    if connection.vendor == "postgresql":
        return "{" + ",".join(str(float(value)) for value in preference_vector) + "}"
    return str(preference_vector)


def _persist_legacy_survey(*, client: "Client", normalized_payload: dict, preference_vector: list[float]) -> SimpleNamespace | None:
    if not _legacy_survey_writable():
        return None

    legacy_client_id = get_legacy_client_id(client=client)
    if not legacy_client_id:
        return None

    existing = (
        LegacyClientSurvey.objects.filter(client_id=legacy_client_id)
        .order_by("-created_at_ts", "-survey_id")
        .first()
    )
    created_at = timezone.now()
    survey_id = existing.survey_id if existing is not None else _next_legacy_pk(LegacyClientSurvey, "survey_id")
    LegacyClientSurvey.objects.update_or_create(
        survey_id=survey_id,
        defaults={
            "client_id": legacy_client_id,
            "hair_length": normalized_payload.get("target_length"),
            "hair_mood": normalized_payload.get("target_vibe"),
            "hair_condition": normalized_payload.get("scalp_type"),
            "hair_color": normalized_payload.get("hair_colour"),
            "budget": normalized_payload.get("budget_range"),
            "preference_vector": _legacy_preference_vector_storage(preference_vector),
            "updated_at": created_at.isoformat(),
            "backend_survey_id": None,
            "backend_client_ref_id": client.id,
            "target_length": normalized_payload.get("target_length"),
            "target_vibe": normalized_payload.get("target_vibe"),
            "scalp_type": normalized_payload.get("scalp_type"),
            "hair_colour": normalized_payload.get("hair_colour"),
            "budget_range": normalized_payload.get("budget_range"),
            "preference_vector_json": preference_vector,
            "created_at_ts": created_at,
        },
    )
    return _legacy_survey_namespace(
        survey_id=survey_id,
        client=client,
        normalized_payload=normalized_payload,
        preference_vector=preference_vector,
        created_at=created_at,
    )


def _legacy_result_detail_candidates(*, recommendation_id: int) -> list[LegacyClientResultDetail]:
    return list(
        LegacyClientResultDetail.objects.filter(
            Q(detail_id=recommendation_id) | Q(backend_recommendation_id=recommendation_id)
        ).order_by("-detail_id")
    )


def _legacy_result_and_detail_for_recommendation(*, client: "Client", recommendation_id: int) -> tuple[LegacyClientResult | None, LegacyClientResultDetail | None]:
    legacy_client_id = get_legacy_client_id(client=client)
    if not legacy_client_id:
        return None, None
    for detail in _legacy_result_detail_candidates(recommendation_id=recommendation_id):
        result_row = LegacyClientResult.objects.filter(result_id=detail.result_id, client_id=legacy_client_id).first()
        if result_row is not None:
            return result_row, detail
    return None, None


def _legacy_result_and_detail_for_style(*, client: "Client", style_id: int) -> tuple[LegacyClientResult | None, LegacyClientResultDetail | None]:
    legacy_client_id = get_legacy_client_id(client=client)
    if not legacy_client_id:
        return None, None
    result_rows = list(
        LegacyClientResult.objects.filter(client_id=legacy_client_id).order_by("-updated_at", "-result_id")
    )
    for result_row in result_rows:
        detail = (
            LegacyClientResultDetail.objects.filter(result_id=result_row.result_id, hairstyle_id=style_id)
            .order_by("rank", "detail_id")
            .first()
        )
        if detail is not None:
            return result_row, detail
    return None, None


def _legacy_recommendation_namespace(
    *,
    client: "Client",
    capture_record,
    batch_id,
    created_at,
    item: dict,
    detail_id: int,
) -> SimpleNamespace:
    style = get_style_record(style_id=item["style_id"])
    return SimpleNamespace(
        id=detail_id,
        client=client,
        client_id=client.id,
        capture_record=_resolve_capture_record_relation(capture_record),
        capture_record_id=getattr(capture_record, "id", None),
        style=style,
        batch_id=batch_id,
        source="generated",
        style_id_snapshot=item["style_id"],
        style_name_snapshot=item["style_name"],
        style_description_snapshot=item.get("style_description", ""),
        keywords=list(item.get("keywords") or []),
        sample_image_url=item.get("sample_image_url"),
        simulation_image_url=item.get("simulation_image_url"),
        regeneration_snapshot=item.get("regeneration_snapshot"),
        llm_explanation=item.get("llm_explanation"),
        reasoning_snapshot=dict(item.get("reasoning_snapshot") or {}),
        match_score=item.get("match_score"),
        rank=item.get("rank", 0),
        is_chosen=False,
        chosen_at=None,
        is_sent_to_admin=False,
        sent_at=None,
        created_at=created_at,
    )


def _persist_legacy_generated_batch(
    *,
    client: "Client",
    capture_record,
    survey,
    analysis,
    items: list[dict],
    regeneration_snapshot: dict,
    recommendation_stage: str,
) -> tuple[str, list[SimpleNamespace]] | None:
    if not _legacy_result_writable():
        return None

    legacy_client_id = get_legacy_client_id(client=client)
    if not legacy_client_id:
        return None

    created_at = timezone.now()
    batch_id = uuid.uuid4()
    result_id = _next_legacy_pk(LegacyClientResult, "result_id")
    next_detail_id = _next_legacy_pk(LegacyClientResultDetail, "detail_id")
    analysis_id = getattr(analysis, "id", None) or getattr(analysis, "analysis_id", None) or 0
    survey_snapshot = {
        "target_length": getattr(survey, "target_length", None),
        "target_vibe": getattr(survey, "target_vibe", None),
        "scalp_type": getattr(survey, "scalp_type", None),
        "hair_colour": getattr(survey, "hair_colour", None),
        "budget_range": getattr(survey, "budget_range", None),
        "preference_vector": getattr(survey, "preference_vector", None) or [],
    }
    analysis_snapshot = {
        "face_shape": getattr(analysis, "face_shape", None),
        "golden_ratio": getattr(analysis, "golden_ratio_score", None),
        "image_url": resolve_storage_reference(getattr(analysis, "image_url", None)),
        "landmark_snapshot": getattr(analysis, "landmark_snapshot", None) or {},
    }

    LegacyClientResult.objects.create(
        result_id=result_id,
        analysis_id=analysis_id,
        client_id=legacy_client_id,
        selected_hairstyle_id=None,
        selected_image_url=None,
        is_confirmed=False,
        created_at=created_at.isoformat(),
        updated_at=created_at.isoformat(),
        backend_selection_id=None,
        backend_consultation_id=None,
        backend_client_ref_id=client.id,
        backend_admin_ref_id=client.shop_id,
        backend_designer_ref_id=client.designer_id,
        source="generated",
        survey_snapshot=survey_snapshot,
        analysis_data_snapshot=analysis_snapshot,
        status="READY",
        is_active=False,
        is_read=True,
        closed_at=None,
        selected_recommendation_id=None,
    )

    rows: list[SimpleNamespace] = []
    for item in items:
        detail_id = next_detail_id
        next_detail_id += 1
        reasoning_snapshot = dict(item.get("reasoning_snapshot") or {})
        reasoning_snapshot["recommendation_stage"] = recommendation_stage
        LegacyClientResultDetail.objects.create(
            detail_id=detail_id,
            result_id=result_id,
            hairstyle_id=item["style_id"],
            rank=item.get("rank", 0),
            similarity_score=float(item.get("match_score") or 0.0),
            final_score=float(item.get("match_score") or 0.0),
            simulated_image_url=None,
            recommendation_reason=reasoning_snapshot.get("summary") or item.get("llm_explanation") or "",
            backend_recommendation_id=None,
            backend_client_ref_id=client.id,
            backend_capture_record_id=getattr(capture_record, "id", None),
            batch_id=batch_id,
            source="generated",
            style_name_snapshot=item["style_name"],
            style_description_snapshot=item.get("style_description", ""),
            keywords_json=list(item.get("keywords") or []),
            sample_image_url=None,
            regeneration_snapshot=regeneration_snapshot,
            reasoning_snapshot=reasoning_snapshot,
            is_chosen=False,
            chosen_at=None,
            is_sent_to_admin=False,
            sent_at=None,
            created_at_ts=created_at,
        )
        rows.append(
            _legacy_recommendation_namespace(
                client=client,
                capture_record=capture_record,
                batch_id=batch_id,
                created_at=created_at,
                item={
                    **item,
                    "reasoning_snapshot": reasoning_snapshot,
                    "regeneration_snapshot": regeneration_snapshot,
                    "simulation_image_url": None,
                    "sample_image_url": None,
                },
                detail_id=detail_id,
            )
        )

    return str(batch_id), rows


def _legacy_style_label(style_id: int) -> tuple[str, str]:
    reference = _style_reference(style_id)
    return reference["style_name"], reference["style_description"]


def _normalize_text_value(value: object) -> str:
    return str(value or "").strip()


def _survey_payload_from_gender_questions(*, client: "Client", payload: dict) -> dict | None:
    q1 = _normalize_text_value(payload.get("q1"))
    q2 = _normalize_text_value(payload.get("q2"))
    q3 = _normalize_text_value(payload.get("q3"))
    q4 = _normalize_text_value(payload.get("q4"))
    q5 = _normalize_text_value(payload.get("q5"))
    q6 = _normalize_text_value(payload.get("q6"))

    if not any((q1, q2, q3, q4, q5, q6)):
        return None

    gender = _normalize_text_value(getattr(client, "gender", None)).lower()

    is_male = gender in {"male", "m"}

    if is_male:
        target_length_map = {
            "아주 짧고 깔끔하게": "short",
            "너무 짧지 않게 자연스럽게": "medium",
            "길이감 있게 남기고 싶음": "long",
        }
        target_vibe_map = {
            "단정한": "chic",
            "부드러운": "natural",
            "트렌디한": "chic",
        }
        scalp_type_map = {
            "펌 없이 깔끔하게": "straight",
            "자연스러운 볼륨 정도": "waved",
            "컬감이 느껴지는 스타일": "curly",
        }
    else:
        target_length_map = {
            "짧게": "short",
            "중간 길이": "medium",
            "길게": "long",
            "유지": "medium",
        }
        target_vibe_map = {
            "내추럴한": "natural",
            "세련된": "chic",
            "사랑스러운": "cute",
            "고급스러운": "elegant",
        }
        scalp_type_map = {
            "생머리 느낌": "straight",
            "끝선 위주 자연스러운 컬": "waved",
            "전체적으로 웨이브감": "curly",
        }

    mapped_payload = {
        "target_length": target_length_map.get(q1, "unknown"),
        "target_vibe": target_vibe_map.get(q6 if is_male else q5, "unknown"),
        "scalp_type": scalp_type_map.get(q5 if is_male else q4, "unknown"),
        "hair_colour": "unknown",
        "budget_range": "unknown",
    }

    logger.info(
        "[survey_question_mapping] client_id=%s gender=%s target_length=%s target_vibe=%s scalp_type=%s",
        client.id,
        gender or "unknown",
        mapped_payload["target_length"],
        mapped_payload["target_vibe"],
        mapped_payload["scalp_type"],
    )
    return mapped_payload


def normalize_survey_payload(*, client: "Client", payload: dict) -> dict:
    if any(payload.get(field) for field in ("target_length", "target_vibe", "scalp_type", "hair_colour", "budget_range")):
        return {
            "target_length": payload.get("target_length"),
            "target_vibe": payload.get("target_vibe"),
            "scalp_type": payload.get("scalp_type"),
            "hair_colour": payload.get("hair_colour"),
            "budget_range": payload.get("budget_range"),
        }

    mapped_payload = _survey_payload_from_gender_questions(client=client, payload=payload)
    if mapped_payload is not None:
        return mapped_payload

    return {
        "target_length": payload.get("target_length"),
        "target_vibe": payload.get("target_vibe"),
        "scalp_type": payload.get("scalp_type"),
        "hair_colour": payload.get("hair_colour"),
        "budget_range": payload.get("budget_range"),
    }


def get_latest_capture_attempt(client: "Client"):
    return get_latest_capture(client)


def _resolve_capture_record_relation(capture_record) -> "CaptureRecord | None":
    return capture_record


def build_survey_snapshot(client: "Client") -> dict | None:
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
    client: "Client",
    survey,
    analysis: "FaceAnalysis | None",
    source: str,
    capture_record: "CaptureRecord | None" = None,
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


def upsert_survey(client: "Client", payload: dict) -> "Survey":
    normalized_payload = normalize_survey_payload(client=client, payload=payload)
    preference_vector = build_preference_vector(
        target_length=normalized_payload.get("target_length"),
        target_vibe=normalized_payload.get("target_vibe"),
        scalp_type=normalized_payload.get("scalp_type"),
        hair_colour=normalized_payload.get("hair_colour"),
        budget_range=normalized_payload.get("budget_range"),
    )
    legacy_survey = _persist_legacy_survey(
        client=client,
        normalized_payload=normalized_payload,
        preference_vector=preference_vector,
    )
    if legacy_survey is not None:
        return legacy_survey
    return _legacy_survey_namespace(
        survey_id=0,
        client=client,
        normalized_payload=normalized_payload,
        preference_vector=preference_vector,
        created_at=timezone.now(),
    )


def persist_generated_batch(
    *,
    client: "Client",
    capture_record: "CaptureRecord | None",
    survey,
    analysis: "FaceAnalysis",
    recommendation_stage: str = "initial",
) -> tuple[str, list["FormerRecommendation"]]:
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
    relation_capture_record = _resolve_capture_record_relation(capture_record)

    legacy_result = _persist_legacy_generated_batch(
        client=client,
        capture_record=relation_capture_record,
        survey=survey,
        analysis=analysis,
        items=items,
        regeneration_snapshot=regeneration_snapshot,
        recommendation_stage=recommendation_stage,
    )
    if legacy_result is not None:
        return legacy_result
    raise RuntimeError("Legacy result tables are required for recommendation writes.")


def serialize_recommendation_row(row: "FormerRecommendation") -> dict:
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
        "legacy_client_id": get_legacy_client_id(client=row.client),
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


def _serialize_row(row: "FormerRecommendation") -> dict:
    return serialize_recommendation_row(row)


def _get_recommendation_stage(rows: "list[FormerRecommendation]") -> str:
    if not rows:
        return "initial"
    snapshot = rows[0].reasoning_snapshot or {}
    return str(snapshot.get("recommendation_stage") or "initial")


def _build_retry_recommendation_meta(*, rows: "list[FormerRecommendation]", has_active_consultation: bool) -> dict:
    recommendation_stage = _get_recommendation_stage(rows)
    attempts_used = 1 if recommendation_stage == "retry" else 0
    has_selection = any(row.is_chosen for row in rows)
    can_retry = bool(rows) and recommendation_stage == "initial" and not has_active_consultation and not has_selection
    remaining_count = max(0, RETRY_RECOMMENDATION_MAX_ATTEMPTS - attempts_used) if can_retry else 0

    if not rows:
        retry_state = "not_ready"
        retry_block_reason = "initial_recommendations_missing"
    elif has_active_consultation:
        retry_state = "consultation_locked"
        retry_block_reason = "consultation_started"
    elif has_selection:
        retry_state = "selection_locked"
        retry_block_reason = "recommendation_already_selected"
    elif recommendation_stage == "retry":
        retry_state = "retry_consumed"
        retry_block_reason = "retry_already_used"
    else:
        retry_state = "available"
        retry_block_reason = None

    return {
        "recommendation_stage": recommendation_stage,
        "can_retry_recommendations": can_retry,
        "retry_state": retry_state,
        "consultation_locked": has_active_consultation,
        "retry_block_reason": retry_block_reason,
        "retry_recommendations_remaining_count": remaining_count,
        "retry_recommendations_policy": {
            **RETRY_RECOMMENDATION_POLICY,
            "attempts_allowed": RETRY_RECOMMENDATION_MAX_ATTEMPTS,
            "attempts_used": attempts_used,
        },
    }


def _legacy_recommendation_stage(items: list[dict]) -> str:
    if not items:
        return "initial"
    snapshot = dict(items[0].get("reasoning_snapshot") or {})
    return str(snapshot.get("recommendation_stage") or "initial")


def _build_legacy_retry_recommendation_meta(*, items: list[dict], has_active_consultation: bool) -> dict:
    recommendation_stage = _legacy_recommendation_stage(items)
    attempts_used = 1 if recommendation_stage == "retry" else 0
    has_selection = any(bool(item.get("is_chosen")) for item in items)
    is_generated = all(str(item.get("source") or "").startswith("generated") for item in items)
    can_retry = bool(items) and is_generated and recommendation_stage == "initial" and not has_active_consultation and not has_selection

    if not items:
        retry_state = "not_ready"
        retry_block_reason = "initial_recommendations_missing"
    elif has_active_consultation:
        retry_state = "consultation_locked"
        retry_block_reason = "consultation_started"
    elif has_selection:
        retry_state = "selection_locked"
        retry_block_reason = "recommendation_already_selected"
    elif recommendation_stage == "retry":
        retry_state = "retry_consumed"
        retry_block_reason = "retry_already_used"
    elif not is_generated:
        retry_state = "legacy_locked"
        retry_block_reason = "legacy_result_only"
    else:
        retry_state = "available"
        retry_block_reason = None

    return {
        "recommendation_stage": recommendation_stage,
        "can_retry_recommendations": can_retry,
        "retry_state": retry_state,
        "consultation_locked": has_active_consultation,
        "retry_block_reason": retry_block_reason,
        "retry_recommendations_remaining_count": (
            max(0, RETRY_RECOMMENDATION_MAX_ATTEMPTS - attempts_used)
            if can_retry else 0
        ),
        "retry_recommendations_policy": (
            {
                **RETRY_RECOMMENDATION_POLICY,
                "attempts_allowed": RETRY_RECOMMENDATION_MAX_ATTEMPTS,
                "attempts_used": attempts_used,
            }
            if is_generated else None
        ),
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


def serialize_capture_status(record: "CaptureRecord") -> dict:
    privacy_snapshot = record.privacy_snapshot or {}
    payload = {
        "record_id": record.id,
        "client_id": record.client_id,
        "legacy_client_id": get_legacy_client_id(client=record.client),
        "status": record.status.lower(),
        "face_count": record.face_count,
        "error_note": record.error_note,
        "landmark_snapshot": record.landmark_snapshot,
        "deidentified_image_url": resolve_storage_reference(record.deidentified_path),
        "privacy_snapshot": privacy_snapshot,
        "image_storage_policy": privacy_snapshot.get("storage_policy", "asset_store"),
        "storage_snapshot": build_storage_snapshot(
            original_path=record.original_path,
            processed_path=record.processed_path,
            deidentified_path=record.deidentified_path,
        ),
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
    selected_legacy_client = None
    selected_legacy_item = None
    if recommendation_id is not None:
        legacy_client, legacy_item = find_legacy_recommendation_context(recommendation_id=recommendation_id)
        if legacy_client is None or legacy_item is None:
            raise ValueError("The selected recommendation could not be found.")
        selected_legacy_client = legacy_client
        selected_legacy_item = legacy_item
        regeneration_snapshot = regeneration_snapshot or dict(selected_legacy_item.get("regeneration_snapshot") or {})
        style_id = style_id or int(selected_legacy_item.get("style_id") or 0)
        attempts_used = int((selected_legacy_item.get("reasoning_snapshot") or {}).get("regeneration_attempts_used") or 0)
        if attempts_used >= REGENERATION_MAX_ATTEMPTS:
            raise ValueError("This recommendation has already used its one allowed regeneration.")

    if not regeneration_snapshot and selected_legacy_client is not None:
        regeneration_snapshot = build_recommendation_regeneration_snapshot(
            client=selected_legacy_client,
            survey=(get_latest_survey(selected_legacy_client) or build_default_survey_context(selected_legacy_client.id)),
            analysis=get_latest_analysis(selected_legacy_client),
            source=str(selected_legacy_item.get("source") or "legacy_bridge"),
            capture_record=get_latest_capture(selected_legacy_client),
            recommendation_stage="legacy",
        )

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

    if selected_legacy_client is not None and selected_legacy_item is not None and recommendation_id is not None:
        result_row, detail_row = _legacy_result_and_detail_for_recommendation(
            client=selected_legacy_client,
            recommendation_id=int(recommendation_id),
        )
        if result_row is None or detail_row is None:
            raise ValueError("The selected recommendation could not be found.")

        reasoning_snapshot = dict(detail_row.reasoning_snapshot or {})
        attempts_used = int(reasoning_snapshot.get("regeneration_attempts_used") or 0) + 1
        reasoning_snapshot["regenerated"] = True
        reasoning_snapshot["regeneration_source"] = regeneration_snapshot.get("source")
        reasoning_snapshot["regeneration_attempts_used"] = attempts_used
        reasoning_snapshot["regeneration_attempts_allowed"] = REGENERATION_MAX_ATTEMPTS
        reasoning_snapshot["regeneration_remaining_count"] = max(0, REGENERATION_MAX_ATTEMPTS - attempts_used)
        reasoning_snapshot["regeneration_policy"] = dict(REGENERATION_POLICY)

        regenerated_score = regenerated_card.get("match_score")
        try:
            regenerated_score = float(
                regenerated_score
                if regenerated_score is not None
                else (detail_row.final_score or detail_row.similarity_score or 0.0)
            )
        except (TypeError, ValueError):
            regenerated_score = float(detail_row.final_score or detail_row.similarity_score or 0.0)

        detail_row.final_score = regenerated_score
        detail_row.similarity_score = regenerated_score
        detail_row.recommendation_reason = (
            regenerated_card.get("llm_explanation")
            or detail_row.recommendation_reason
            or ""
        )
        detail_row.reasoning_snapshot = reasoning_snapshot
        detail_row.regeneration_snapshot = regeneration_snapshot
        detail_row.simulated_image_url = regenerated_card.get("simulation_image_url")
        detail_row.save(
            update_fields=[
                "final_score",
                "similarity_score",
                "recommendation_reason",
                "reasoning_snapshot",
                "regeneration_snapshot",
                "simulated_image_url",
            ]
        )

        refreshed_item = _find_legacy_recommendation_item(
            client=selected_legacy_client,
            recommendation_id=int(recommendation_id),
        ) or selected_legacy_item
        reference_images = list(refreshed_item.get("reference_images") or [])
        if not reference_images and refreshed_item.get("sample_image_url"):
            reference_images.append(
                {
                    "image_url": refreshed_item.get("sample_image_url"),
                    "description": refreshed_item.get("style_description") or "",
                }
            )
        card = {
            **refreshed_item,
            "reference_images": reference_images,
            "simulation_image_url": regenerated_card.get("simulation_image_url"),
            "synthetic_image_url": regenerated_card.get("synthetic_image_url"),
            "llm_explanation": regenerated_card.get("llm_explanation") or refreshed_item.get("llm_explanation") or "",
            "reasoning": regenerated_card.get("reasoning") or refreshed_item.get("reasoning") or "",
            "reasoning_snapshot": reasoning_snapshot,
            "image_policy": "vector_only",
            "can_regenerate_simulation": False,
            "regeneration_remaining_count": max(0, REGENERATION_MAX_ATTEMPTS - attempts_used),
            "regeneration_policy": {
                **REGENERATION_POLICY,
                "attempts_allowed": REGENERATION_MAX_ATTEMPTS,
                "attempts_used": attempts_used,
            },
            "match_score": regenerated_score,
        }
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
        "recommendation_id": (
            int(selected_legacy_item["recommendation_id"]) if selected_legacy_item else None
        ),
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


def get_former_recommendations(client: "Client") -> dict:
    legacy_items = get_legacy_former_recommendation_items(client=client) or []
    if not legacy_items:
        return _build_empty_response(
            source="former_recommendations",
            message="No previous recommendation history is available yet.",
            next_actions=["trend", "capture"],
        )
    return {
        "status": "ready",
        "client_id": client.id,
        "legacy_client_id": get_legacy_client_id(client=client),
        "source": "former_recommendations",
        "items": legacy_items[:5],
    }


def _ensure_current_batch(
    client: "Client",
    *,
    latest_capture,
    latest_survey,
    latest_analysis,
    legacy_items: list[dict],
) -> tuple[str | None, list[dict], str | None]:
    if not latest_capture or not latest_analysis:
        return None, [], "needs_capture"

    if legacy_items:
        return str(legacy_items[0].get("batch_id") or ""), legacy_items, None

    survey_context = latest_survey or build_default_survey_context(client.id)
    batch_id, _ = persist_generated_batch(
        client=client,
        capture_record=latest_capture,
        survey=survey_context,
        analysis=latest_analysis,
    )
    refreshed_items = get_legacy_former_recommendation_items(client=client) or []
    return batch_id, refreshed_items, None


def _build_local_mock_recommendations(*, client: "Client", latest_survey, latest_analysis: "FaceAnalysis | None") -> dict:
    styles_by_id = ensure_catalog_styles()
    mock_style_ids = [profile.style_id for profile in STYLE_CATALOG[:3]]
    if not mock_style_ids:
        return _build_empty_response(
            source="local_mock",
            message="Local mock recommendations are enabled, but no style catalog data is available yet.",
            next_action="capture",
        )

    target_vibe = getattr(latest_survey, "target_vibe", None) or "natural"
    target_length = getattr(latest_survey, "target_length", None) or "medium"
    face_shape = getattr(latest_analysis, "face_shape", None) or "balanced"
    items: list[dict] = []

    for rank, style_id in enumerate(mock_style_ids, start=1):
        reference = _style_reference(style_id, styles_by_id=styles_by_id)
        image_url = reference["sample_image_url"]
        items.append(
            {
                "recommendation_id": None,
                "batch_id": None,
                "source": "local_mock",
                "style_id": style_id,
                "style_name": reference["style_name"],
                "style_description": reference["style_description"],
                "keywords": reference["keywords"],
                "sample_image_url": image_url,
                "reference_images": (
                    [{"image_url": image_url, "description": reference["style_description"]}] if image_url else []
                ),
                "simulation_image_url": image_url,
                "synthetic_image_url": image_url,
                "llm_explanation": "로컬 테스트용 예시 결과입니다. 실제 모델 결과가 연결되면 이 설명은 교체됩니다.",
                "reasoning": f"로컬 테스트용 예시 결과입니다. {target_length} 길이감과 {target_vibe} 분위기, {face_shape} 인상을 기준으로 표시했습니다.",
                "reasoning_snapshot": {
                    "source": "local_mock",
                    "is_mock": True,
                    "client_id": client.id,
                },
                "image_policy": "local_mock",
                "can_regenerate_simulation": False,
                "regeneration_remaining_count": 0,
                "regeneration_policy": None,
                "match_score": float(max(70, 95 - ((rank - 1) * 7))),
                "rank": rank,
                "is_chosen": False,
                "created_at": timezone.now(),
            }
        )

    return {
        "status": "ready",
        "client_id": client.id,
        "legacy_client_id": get_legacy_client_id(client=client),
        "source": "local_mock",
        "batch_id": None,
        "message": "Local mock recommendations are being shown because the analysis result is not ready yet.",
        "items": items,
        "next_actions": ["consultation"],
    }


def _has_active_consultation_state(*, client: "Client") -> bool:
    return bool(get_legacy_active_consultation_items(client=client))


def _coerce_batch_uuid(value: object) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    text = str(value or "").strip()
    if text:
        try:
            return uuid.UUID(text)
        except (TypeError, ValueError, AttributeError):
            return uuid.uuid5(uuid.NAMESPACE_URL, f"legacy-batch:{text}")
    return uuid.uuid4()


def _find_legacy_recommendation_item(
    *,
    client: "Client",
    recommendation_id: int | None = None,
    style_id: int | None = None,
) -> dict | None:
    items = get_legacy_former_recommendation_items(client=client)
    if not items:
        return None

    if recommendation_id is not None:
        recommendation_key = str(recommendation_id)
        return next(
            (item for item in items if str(item.get("recommendation_id")) == recommendation_key),
            None,
        )

    if style_id is not None:
        return next((item for item in items if int(item.get("style_id") or 0) == int(style_id)), None)

    return next((item for item in items if item.get("is_chosen")), items[0])


def _bridge_recommendation_from_legacy_item(
    *,
    client: "Client",
    legacy_item: dict,
    latest_analysis: "FaceAnalysis | None" = None,
) -> "FormerRecommendation":
    style_id = int(legacy_item.get("style_id") or 0)
    style_reference = get_style_record(style_id=style_id)
    latest_capture = get_latest_capture(client)
    latest_survey = get_latest_survey(client) or build_default_survey_context(client.id)
    latest_analysis = latest_analysis or get_latest_analysis(client)
    regeneration_snapshot = build_recommendation_regeneration_snapshot(
        client=client,
        survey=latest_survey,
        analysis=latest_analysis,
        source=str(legacy_item.get("source") or "legacy_bridge"),
        capture_record=latest_capture,
        recommendation_stage="legacy",
    )
    reasoning_snapshot = {
        **dict(legacy_item.get("reasoning_snapshot") or {}),
        "summary": (
            (legacy_item.get("reasoning_snapshot") or {}).get("summary")
            or legacy_item.get("reasoning")
            or legacy_item.get("llm_explanation")
            or ""
        ),
        "legacy_bridge": True,
    }
    return SimpleNamespace(
        id=int(legacy_item.get("recommendation_id") or 0),
        client=client,
        client_id=client.id,
        capture_record=latest_capture,
        capture_record_id=getattr(latest_capture, "id", None),
        style=style_reference,
        batch_id=_coerce_batch_uuid(legacy_item.get("batch_id")),
        source=str(legacy_item.get("source") or "legacy_bridge")[:20],
        style_id_snapshot=style_id,
        style_name_snapshot=(
            legacy_item.get("style_name")
            or getattr(style_reference, "name", None)
            or getattr(style_reference, "style_name", None)
            or f"Style {style_id}"
        ),
        style_description_snapshot=(
            legacy_item.get("style_description")
            or getattr(style_reference, "description", None)
            or ""
        ),
        keywords=list(
            legacy_item.get("keywords")
            or ([getattr(style_reference, "vibe", None)] if getattr(style_reference, "vibe", None) else [])
        ),
        sample_image_url=legacy_item.get("sample_image_url") or getattr(style_reference, "image_url", None),
        simulation_image_url=legacy_item.get("simulation_image_url"),
        regeneration_snapshot=regeneration_snapshot,
        llm_explanation=legacy_item.get("llm_explanation") or legacy_item.get("reasoning") or "",
        reasoning_snapshot=reasoning_snapshot,
        match_score=legacy_item.get("match_score"),
        rank=int(legacy_item.get("rank") or 1),
        is_chosen=bool(legacy_item.get("is_chosen")),
        chosen_at=legacy_item.get("chosen_at"),
        is_sent_to_admin=bool(legacy_item.get("is_sent_to_admin")),
        sent_at=legacy_item.get("sent_at"),
        created_at=legacy_item.get("created_at"),
    )


def _mark_recommendation_batch_as_selected(*, selected_row: "FormerRecommendation") -> "FormerRecommendation":
    if has_legacy_result_source():
        result_row, detail_row = _legacy_result_and_detail_for_recommendation(
            client=selected_row.client,
            recommendation_id=int(selected_row.id),
        )
        now = timezone.now()
        if result_row is not None:
            LegacyClientResultDetail.objects.filter(result_id=result_row.result_id).update(
                is_chosen=False,
                chosen_at=None,
                is_sent_to_admin=False,
                sent_at=None,
            )
        if detail_row is not None:
            detail_row.is_chosen = True
            detail_row.chosen_at = now
            detail_row.is_sent_to_admin = True
            detail_row.sent_at = now
            detail_row.save(update_fields=["is_chosen", "chosen_at", "is_sent_to_admin", "sent_at"])
            selected_row.is_chosen = True
            selected_row.chosen_at = now
            selected_row.is_sent_to_admin = True
            selected_row.sent_at = now
    return selected_row


def _build_legacy_current_recommendations_payload(
    *,
    client: "Client",
    legacy_items: list[dict],
    has_active_consultation: bool,
    message: str,
) -> dict:
    retry_meta = _build_legacy_retry_recommendation_meta(
        items=legacy_items,
        has_active_consultation=has_active_consultation,
    )
    return {
        "status": "ready",
        "client_id": client.id,
        "legacy_client_id": get_legacy_client_id(client=client),
        "source": "current_recommendations",
        "batch_id": legacy_items[0].get("batch_id"),
        "message": message,
        "items": legacy_items,
        "next_actions": (
            ["retry_recommendations", "consultation"]
            if retry_meta["can_retry_recommendations"]
            else ["consultation"]
        ),
        **retry_meta,
    }


def get_current_recommendations(client: "Client") -> dict:
    latest_capture_attempt = get_latest_capture_attempt(client)
    latest_survey = get_latest_survey(client)
    latest_capture = get_latest_capture(client)
    latest_analysis = get_latest_analysis(client)
    legacy_items = get_legacy_former_recommendation_items(client=client) or []

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
        if legacy_items:
            has_active_consultation = _has_active_consultation_state(client=client)
            return _build_legacy_current_recommendations_payload(
                client=client,
                legacy_items=legacy_items,
                has_active_consultation=has_active_consultation,
                message="Legacy model-team recommendation data is being shown while canonical recommendation records are not available.",
            )
        if settings.DEBUG and settings.MIRRAI_LOCAL_MOCK_RESULTS and latest_capture:
            return _build_local_mock_recommendations(
                client=client,
                latest_survey=latest_survey,
                latest_analysis=latest_analysis,
            )
        return {
            "status": "needs_capture",
            "source": "current_recommendations",
            "message": "A valid front-facing capture is required before we can generate the current Top-5 recommendations.",
            "next_action": "capture",
            "items": [],
        }

    if legacy_items:
        has_active_consultation = _has_active_consultation_state(client=client)
        return _build_legacy_current_recommendations_payload(
            client=client,
            legacy_items=legacy_items,
            has_active_consultation=has_active_consultation,
            message="Existing model-team recommendation data is being reused.",
        )

    batch_id, rows, status_code = _ensure_current_batch(
        client,
        latest_capture=latest_capture,
        latest_survey=latest_survey,
        latest_analysis=latest_analysis,
        legacy_items=legacy_items,
    )
    if status_code == "needs_capture":
        return {
            "status": "needs_capture",
            "source": "current_recommendations",
            "message": "Capture data is not ready yet. Please complete capture before requesting current recommendations.",
            "next_action": "capture",
            "items": [],
        }

    if not rows:
        if settings.DEBUG and settings.MIRRAI_LOCAL_MOCK_RESULTS:
            return _build_local_mock_recommendations(
                client=client,
                latest_survey=latest_survey,
                latest_analysis=latest_analysis,
            )
        return _build_empty_response(
            source="current_recommendations",
            message="No recommendation batch is available yet. Please retake the capture and try again.",
            next_action="capture",
        )

    has_active_consultation = _has_active_consultation_state(client=client)
    retry_meta = _build_legacy_retry_recommendation_meta(
        items=rows,
        has_active_consultation=has_active_consultation,
    )
    message = "The latest Top-5 recommendations were generated from the most recent capture and analysis."
    if latest_survey is None:
        message = "The latest Top-5 recommendations were generated from face analysis only because survey data is not available."
    elif retry_meta["recommendation_stage"] == "retry":
        message = "The recommendations were regenerated once with preference-first scoring and no trend influence."

    payload = {
        "status": "ready",
        "client_id": client.id,
        "legacy_client_id": get_legacy_client_id(client=client),
        "source": "current_recommendations",
        "batch_id": batch_id,
        "message": message,
        "items": rows,
    }
    payload.update(retry_meta)
    payload["next_actions"] = (
        ["retry_recommendations", "consultation"]
        if retry_meta["can_retry_recommendations"]
        else ["consultation"]
    )
    return payload


def retry_current_recommendations(client: "Client") -> dict:
    latest_capture = get_latest_capture(client)
    latest_analysis = get_latest_analysis(client)
    latest_survey = get_latest_survey(client)
    if not latest_capture or not latest_analysis:
        raise ValueError("A completed capture and face analysis are required before retrying recommendations.")

    legacy_items = get_legacy_former_recommendation_items(client=client) or []
    if not legacy_items:
        raise ValueError("Retry is available only after the initial recommendation batch has been generated.")
    retry_meta = _build_legacy_retry_recommendation_meta(
        items=legacy_items,
        has_active_consultation=_has_active_consultation_state(client=client),
    )
    if not retry_meta["can_retry_recommendations"]:
        if retry_meta["retry_block_reason"] == "consultation_started":
            raise ValueError("Retry is not available after the consultation flow has started.")
        if retry_meta["retry_block_reason"] == "recommendation_already_selected":
            raise ValueError("Retry is not available after a recommendation has already been selected.")
        if retry_meta["retry_block_reason"] == "retry_already_used":
            raise ValueError("Retry recommendations are only available once after the initial recommendation batch.")
        raise ValueError("Retry is not available while only legacy recommendation data is available.")

    survey_context = latest_survey or build_default_survey_context(client.id)
    new_batch_id, _ = persist_generated_batch(
        client=client,
        capture_record=latest_capture,
        survey=survey_context,
        analysis=latest_analysis,
        recommendation_stage="retry",
    )
    new_items = get_legacy_former_recommendation_items(client=client) or []
    return {
        "status": "ready",
        "client_id": client.id,
        "legacy_client_id": get_legacy_client_id(client=client),
        "source": "current_recommendations",
        "batch_id": new_batch_id,
        "message": "A one-time retry recommendation batch has been generated with preference-first scoring.",
        "items": new_items,
        "next_actions": ["consultation"],
        **_build_legacy_retry_recommendation_meta(
            items=new_items,
            has_active_consultation=False,
        ),
    }


def get_trend_recommendations(*, days: int = 30, client: "Client | None" = None) -> dict:
    cutoff = timezone.now() - timezone.timedelta(days=days)
    target_age_profile = build_client_age_profile(client) if client else None
    legacy_items = get_legacy_confirmed_selection_items(since=cutoff) or []
    selections = legacy_items

    scoped_selections = selections
    trend_scope = "global"
    if target_age_profile:
        exact_group_matches = [
            row
            for row in selections
            if (row.get("age_profile") or {}).get("age_group") == target_age_profile["age_group"]
        ]
        decade_matches = [
            row
            for row in selections
            if (row.get("age_profile") or {}).get("age_decade") == target_age_profile["age_decade"]
        ]
        if exact_group_matches:
            scoped_selections = exact_group_matches
            trend_scope = "age_group"
        elif decade_matches:
            scoped_selections = decade_matches
            trend_scope = "age_decade"

    popular_style_ids = []
    if scoped_selections:
        counts = Counter(row["style_id"] for row in scoped_selections)
        popular_style_ids = [
            {"style_id": style_id, "selection_count": count}
            for style_id, count in counts.most_common(5)
        ]

    items: list[dict] = []
    legacy_representative = {}
    for row in scoped_selections:
        legacy_representative.setdefault(row["style_id"], row)
    for rank, item in enumerate(popular_style_ids, start=1):
        style = get_style_record(style_id=item["style_id"])
        legacy_row = legacy_representative.get(item["style_id"], {})
        if not style and not legacy_row:
            continue
        trend_summary = f"recent confirmed selections in the last {days} days"
        if trend_scope == "age_group" and target_age_profile:
            trend_summary = f"{target_age_profile['age_group']} selections in the last {days} days"
        elif trend_scope == "age_decade" and target_age_profile:
            trend_summary = f"{target_age_profile['age_decade']} selections in the last {days} days"
        items.append(
            {
                "source": "trend",
                "style_id": item["style_id"],
                "style_name": legacy_row.get("style_name") or (style.name if style else f"Style {item['style_id']}"),
                "style_description": legacy_row.get("style_description") or (style.description if style else "") or f"This style has been selected frequently in the last {days} days.",
                "keywords": legacy_row.get("keywords") or ([style.vibe] if style and style.vibe else []),
                "sample_image_url": resolve_storage_reference(legacy_row.get("image_url") or (style.image_url if style else None)),
                "simulation_image_url": resolve_storage_reference(legacy_row.get("image_url") or (style.image_url if style else None)),
                "synthetic_image_url": resolve_storage_reference(legacy_row.get("image_url") or (style.image_url if style else None)),
                "llm_explanation": legacy_row.get("style_description") or (style.description if style else "") or f"This style has been selected frequently in the last {days} days.",
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
        db_seeded = {}
        for style_name in seeded_names:
            style = get_style_record_by_name(style_name=style_name)
            if style is None:
                continue
            normalized_name = str(
                getattr(style, "name", None)
                or getattr(style, "style_name", None)
                or style_name
            ).strip()
            db_seeded[normalized_name] = style

        for rank, seed in enumerate(seed_styles, start=1):
            style = db_seeded.get(str(seed.get("style_name") or "").strip())
            if not style:
                continue
            style_id = int(
                getattr(style, "backend_style_id", None)
                or getattr(style, "hairstyle_id", None)
                or getattr(style, "id", 0)
            )
            style_name = getattr(style, "name", None) or getattr(style, "style_name", None) or ""
            style_description = getattr(style, "description", None) or str(seed.get("description") or "")
            style_image_url = getattr(style, "image_url", None)
            style_vibe = getattr(style, "vibe", None)
            items.append(
                {
                    "source": "trend",
                    "style_id": style_id,
                    "style_name": style_name,
                    "style_description": style_description,
                    "keywords": list(seed.get("keywords") or ([style_vibe] if style_vibe else [])),
                    "sample_image_url": resolve_storage_reference(style_image_url),
                    "simulation_image_url": resolve_storage_reference(style_image_url),
                    "synthetic_image_url": resolve_storage_reference(style_image_url),
                    "llm_explanation": style_description,
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
            normalized_style_id = (
                getattr(style, "backend_style_id", None)
                or getattr(style, "hairstyle_id", None)
                or getattr(style, "id", None)
                or style_id
            )
            style_name = getattr(style, "name", None) or getattr(style, "style_name", None) or f"Style {style_id}"
            style_description = getattr(style, "description", None) or ""
            style_image_url = getattr(style, "image_url", None)
            style_vibe = getattr(style, "vibe", None)
            items.append(
                {
                    "source": "trend",
                    "style_id": normalized_style_id,
                    "style_name": style_name,
                    "style_description": style_description,
                    "keywords": [style_vibe] if style_vibe else [],
                    "sample_image_url": resolve_storage_reference(style_image_url),
                    "simulation_image_url": resolve_storage_reference(style_image_url),
                    "synthetic_image_url": resolve_storage_reference(style_image_url),
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

    payload = {
        "status": "ready",
        "source": "trend",
        "days": days,
        "trend_scope": trend_scope,
        "age_profile": target_age_profile,
        "items": items,
    }
    if client is not None:
        payload["client_id"] = client.id
        payload["legacy_client_id"] = get_legacy_client_id(client=client)
    return payload


def _legacy_result_direct_write(
    *,
    client: "Client",
    selected_style_id: int | None,
    recommendation_id: int | None,
    source: str,
    survey_snapshot: dict | None,
    analysis_snapshot: dict | None,
    admin: "AdminAccount | None",
    designer,
    direct_consultation: bool,
) -> dict | None:
    if not _legacy_result_writable():
        return None

    legacy_client_id = get_legacy_client_id(client=client)
    if not legacy_client_id:
        return None

    now = timezone.now()
    selected_result = None
    selected_detail = None

    if recommendation_id is not None:
        selected_result, selected_detail = _legacy_result_and_detail_for_recommendation(
            client=client,
            recommendation_id=int(recommendation_id),
        )
        if selected_detail is not None:
            selected_style_id = int(selected_detail.hairstyle_id)
    elif source == "current_recommendations" and selected_style_id is not None:
        selected_result, selected_detail = _legacy_result_and_detail_for_style(
            client=client,
            style_id=int(selected_style_id),
        )

    if selected_result is None and source == "trend":
        result_id = _next_legacy_pk(LegacyClientResult, "result_id")
        detail_id = _next_legacy_pk(LegacyClientResultDetail, "detail_id")
        style_name, style_description = _legacy_style_label(int(selected_style_id or 0))
        selected_result = LegacyClientResult.objects.create(
            result_id=result_id,
            analysis_id=(getattr(get_latest_analysis(client), "id", None) or getattr(get_latest_analysis(client), "analysis_id", None) or 0),
            client_id=legacy_client_id,
            selected_hairstyle_id=(None if direct_consultation else selected_style_id),
            selected_image_url=None,
            is_confirmed=not direct_consultation,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
            backend_selection_id=None,
            backend_consultation_id=None,
            backend_client_ref_id=client.id,
            backend_admin_ref_id=(admin.id if admin else client.shop_id),
            backend_designer_ref_id=(designer.id if designer else client.designer_id),
            source=source,
            survey_snapshot=survey_snapshot,
            analysis_data_snapshot=analysis_snapshot,
            status="PENDING",
            is_active=True,
            is_read=False,
            closed_at=None,
            selected_recommendation_id=(None if direct_consultation else detail_id),
        )
        selected_detail = LegacyClientResultDetail.objects.create(
            detail_id=detail_id,
            result_id=result_id,
            hairstyle_id=int(selected_style_id or 0),
            rank=1,
            similarity_score=0.0,
            final_score=0.0,
            simulated_image_url=None,
            recommendation_reason="trend selection promoted to consultation",
            backend_recommendation_id=None,
            backend_client_ref_id=client.id,
            backend_capture_record_id=None,
            batch_id=uuid.uuid4(),
            source=source,
            style_name_snapshot=style_name,
            style_description_snapshot=style_description,
            keywords_json=[],
            sample_image_url=None,
            regeneration_snapshot=None,
            reasoning_snapshot={"summary": "trend selection promoted to consultation", "source": "trend"},
            is_chosen=not direct_consultation,
            chosen_at=(now if not direct_consultation else None),
            is_sent_to_admin=True,
            sent_at=now,
            created_at_ts=now,
        )

    if selected_result is None:
        return None

    LegacyClientResult.objects.filter(client_id=legacy_client_id, is_active=True).exclude(
        result_id=selected_result.result_id
    ).update(
        is_active=False,
        status="CLOSED",
        closed_at=now,
        is_read=True,
    )

    selected_result.selected_hairstyle_id = (None if direct_consultation else selected_style_id)
    selected_result.selected_image_url = (selected_detail.simulated_image_url if selected_detail is not None else None)
    selected_result.is_confirmed = not direct_consultation and selected_style_id is not None
    selected_result.updated_at = now.isoformat()
    selected_result.backend_admin_ref_id = admin.id if admin else client.shop_id
    selected_result.backend_designer_ref_id = designer.id if designer else client.designer_id
    selected_result.source = source
    selected_result.survey_snapshot = survey_snapshot
    selected_result.analysis_data_snapshot = analysis_snapshot
    selected_result.status = "PENDING"
    selected_result.is_active = True
    selected_result.is_read = False
    selected_result.closed_at = None
    selected_result.selected_recommendation_id = (
        selected_detail.detail_id if (selected_detail is not None and not direct_consultation) else None
    )
    selected_result.save()

    LegacyClientResultDetail.objects.filter(result_id=selected_result.result_id).update(
        is_chosen=False,
        chosen_at=None,
        is_sent_to_admin=False,
        sent_at=None,
    )
    if selected_detail is not None:
        selected_detail.backend_client_ref_id = client.id
        selected_detail.is_chosen = not direct_consultation
        selected_detail.chosen_at = (now if not direct_consultation else None)
        selected_detail.is_sent_to_admin = True
        selected_detail.sent_at = now
        selected_detail.save()

    return {
        "consultation_id": selected_result.backend_consultation_id or selected_result.result_id,
        "recommendation_id": (
            (selected_detail.backend_recommendation_id or selected_detail.detail_id)
            if selected_detail is not None
            else None
        ),
        "selected_style_id": selected_style_id,
        "selected_style_name": (
            selected_detail.style_name_snapshot
            if selected_detail is not None
            else None
        ),
    }


def _cancel_legacy_result_directly(*, client: "Client", recommendation_id: int | None = None) -> bool:
    if not _legacy_result_writable():
        return False

    legacy_client_id = get_legacy_client_id(client=client)
    if not legacy_client_id:
        return False

    target_result = None
    if recommendation_id is not None:
        target_result, _ = _legacy_result_and_detail_for_recommendation(
            client=client,
            recommendation_id=int(recommendation_id),
        )

    if target_result is None:
        target_result = (
            LegacyClientResult.objects.filter(client_id=legacy_client_id, is_active=True)
            .order_by("-updated_at", "-result_id")
            .first()
        )
    if target_result is None:
        return False

    now = timezone.now()
    LegacyClientResult.objects.filter(result_id=target_result.result_id).update(
        is_active=False,
        status="CANCELLED",
        closed_at=now,
        is_read=True,
        is_confirmed=False,
        selected_recommendation_id=None,
    )
    LegacyClientResultDetail.objects.filter(result_id=target_result.result_id).update(
        is_chosen=False,
        chosen_at=None,
        is_sent_to_admin=False,
        sent_at=None,
    )
    return True


def confirm_style_selection(
    *,
    client: "Client",
    recommendation_id: int | None = None,
    style_id: int | None = None,
    admin_id: int | str | None = None,
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

    admin = get_admin_by_identifier(identifier=admin_id) if admin_id else None
    if admin is None:
        admin = client.shop
    designer = client.designer
    legacy_direct_result = _legacy_result_direct_write(
        client=client,
        selected_style_id=style_id,
        recommendation_id=recommendation_id,
        source=source,
        survey_snapshot=survey_snapshot,
        analysis_snapshot=analysis_snapshot,
        admin=admin,
        designer=designer,
        direct_consultation=direct_consultation,
    )
    if legacy_direct_result is None:
        raise ValueError("Legacy result tables are required to confirm a selection.")

    selected_style_id = legacy_direct_result["selected_style_id"]
    selected_style_reference = (
        get_style_record(style_id=int(selected_style_id))
        if selected_style_id is not None
        else None
    )

    return {
        "status": "success",
        "consultation_id": legacy_direct_result["consultation_id"],
        "client_id": client.id,
        "legacy_client_id": get_legacy_client_id(client=client),
        "selected_style_id": selected_style_id,
        "selected_style_name": (
            legacy_direct_result["selected_style_name"]
            or getattr(selected_style_reference, "name", None)
            or getattr(selected_style_reference, "style_name", None)
        ),
        "source": source,
        "direct_consultation": direct_consultation,
        "recommendation_id": legacy_direct_result["recommendation_id"],
        "message": (
            "추천 선택 없이 바로 상담 요청이 접수되었습니다."
            if direct_consultation
            else "선택한 스타일과 분석 요약이 상담 요청으로 접수되었습니다."
        ),
    }

def cancel_style_selection(
    *,
    client: "Client",
    recommendation_id: int | None = None,
    source: str = "current_recommendations",
) -> dict:
    if not _cancel_legacy_result_directly(client=client, recommendation_id=recommendation_id):
        raise ValueError("The recommendation to cancel could not be found.")

    return {
        "status": "cancelled",
        "client_id": client.id,
        "legacy_client_id": get_legacy_client_id(client=client),
        "source": source,
        "next_action": "client_input",
        "message": "선택한 스타일이 취소되어 다시 처음 단계로 돌아갈 수 있습니다.",
    }


def run_mirrai_analysis_pipeline(record_id: int, processed_bytes: bytes | None = None):
    try:
        record = mark_legacy_capture_processing(record_id=record_id)
        if record is None or record.status != "PROCESSING":
            return

        storage_snapshot = build_storage_snapshot(
            original_path=record.original_path,
            processed_path=record.processed_path,
            deidentified_path=record.deidentified_path,
        )
        logger.info(
            "[PIPELINE START] Record %s storage_mode=%s bucket=%s path_count=%s",
            record_id,
            storage_snapshot["storage_mode"],
            storage_snapshot["bucket_name"],
            storage_snapshot["path_count"],
        )

        analysis_input_url = resolve_storage_reference(record.processed_path)
        simulated = simulate_face_analysis(
            image_url=analysis_input_url,
            image_bytes=(processed_bytes if record.processed_path is None else None),
        )
        record, analysis = complete_legacy_capture_analysis(
            record_id=record_id,
            face_shape=simulated["face_shape"],
            golden_ratio_score=simulated["golden_ratio_score"],
            landmark_snapshot=(record.landmark_snapshot or simulated.get("landmark_snapshot")),
        )
        if record is None or analysis is None:
            return

        survey = get_latest_survey(record.client) or build_default_survey_context(record.client_id)
        persist_generated_batch(client=record.client, capture_record=record, survey=survey, analysis=analysis)

        sync_model_team_runtime_state(client=record.client)
        logger.info("[PIPELINE SUCCESS] Record %s processed. storage_mode=%s", record_id, storage_snapshot["storage_mode"])

    except Exception as exc:
        logger.error("[PIPELINE ERROR] Record %s: %s", record_id, exc)
        fail_legacy_capture_processing(record_id=record_id, error_note=str(exc))

