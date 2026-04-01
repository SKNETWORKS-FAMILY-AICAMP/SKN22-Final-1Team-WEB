from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from django.db import connection, transaction

from app.models_django import (
    AdminAccount,
    CaptureRecord,
    Client,
    ConsultationRequest,
    Designer,
    FaceAnalysis,
    FormerRecommendation,
    Style,
    StyleSelection,
    Survey,
)


LEGACY_NAMESPACE = uuid.UUID("8c72326e-c379-4c8f-a6ef-3dbb29a4a1f1")
LEGACY_TABLES = [
    "client_result_detail",
    "client_result",
    "client_analysis",
    "client_survey",
    "client",
    "designer",
    "shop",
    "hairstyle",
]


@dataclass(frozen=True)
class LegacySyncSummary:
    shop_count: int
    designer_count: int
    client_count: int
    survey_count: int
    analysis_count: int
    result_count: int
    result_detail_count: int
    hairstyle_count: int


def _legacy_uuid(scope: str, pk: int) -> str:
    return str(uuid.uuid5(LEGACY_NAMESPACE, f"{scope}:{pk}"))


def _supports_postgres_arrays() -> bool:
    return connection.vendor == "postgresql"


def _adapt_array(values):
    if values is None:
        return None
    if _supports_postgres_arrays():
        return list(values)
    return json.dumps(list(values), ensure_ascii=False)


def _adapt_json(value):
    if value in (None, ""):
        return None
    if connection.vendor == "postgresql":
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)


def _legacy_gender(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"m", "male", "man", "남", "남성"}:
        return "M"
    if normalized in {"f", "female", "woman", "여", "여성"}:
        return "F"
    if normalized.startswith("m"):
        return "M"
    if normalized.startswith("f"):
        return "F"
    return "F"


def _score_or_zero(value) -> float:
    return float(value) if value is not None else 0.0


def _table_names() -> set[str]:
    return set(connection.introspection.table_names())


def _existing_legacy_tables() -> list[str]:
    existing = _table_names()
    return [table for table in LEGACY_TABLES if table in existing]


def _latest_capture_by_client() -> dict[int, CaptureRecord]:
    latest: dict[int, CaptureRecord] = {}
    for row in CaptureRecord.objects.order_by("client_id", "-created_at", "-id"):
        latest.setdefault(row.client_id, row)
    return latest


def _capture_for_analysis(analysis: FaceAnalysis, captures_by_client: dict[int, CaptureRecord]) -> CaptureRecord | None:
    return captures_by_client.get(analysis.client_id)


def _latest_analysis_by_client() -> dict[int, FaceAnalysis]:
    latest: dict[int, FaceAnalysis] = {}
    for row in FaceAnalysis.objects.order_by("client_id", "-created_at", "-id"):
        latest.setdefault(row.client_id, row)
    return latest


def _latest_batch_recommendations_by_client() -> dict[int, list[FormerRecommendation]]:
    rows = FormerRecommendation.objects.filter(source="generated").order_by("client_id", "-created_at", "-id")
    grouped: dict[int, list[FormerRecommendation]] = {}
    latest_batch_id_by_client: dict[int, uuid.UUID] = {}
    for row in rows:
        batch_id = latest_batch_id_by_client.setdefault(row.client_id, row.batch_id)
        if row.batch_id == batch_id:
            grouped.setdefault(row.client_id, []).append(row)
    for client_id, items in grouped.items():
        grouped[client_id] = sorted(items, key=lambda item: (item.rank, item.id))
    return grouped


def _latest_selection_by_client() -> dict[int, StyleSelection]:
    latest: dict[int, StyleSelection] = {}
    for row in StyleSelection.objects.order_by("client_id", "-created_at", "-id"):
        latest.setdefault(row.client_id, row)
    return latest


def _latest_consultation_by_client() -> dict[int, ConsultationRequest]:
    latest: dict[int, ConsultationRequest] = {}
    for row in ConsultationRequest.objects.order_by("client_id", "-created_at", "-id"):
        latest.setdefault(row.client_id, row)
    return latest


def _build_shop_rows():
    for admin in AdminAccount.objects.order_by("id"):
        admin_pin = admin.phone[-4:] if admin.phone else "0000"
        yield (
            _legacy_uuid("shop", admin.id),
            admin.phone,
            admin.store_name,
            admin.business_number,
            admin.phone,
            admin.password_hash,
            admin_pin,
            admin.created_at,
            admin.created_at,
        )


def _build_designer_rows():
    for designer in Designer.objects.select_related("shop").order_by("id"):
        yield (
            _legacy_uuid("designer", designer.id),
            _legacy_uuid("shop", designer.shop_id),
            designer.name,
            designer.phone,
            designer.pin_hash,
            designer.is_active,
            designer.created_at,
            designer.created_at,
        )


def _build_client_rows():
    for client in Client.objects.order_by("id"):
        yield (
            _legacy_uuid("client", client.id),
            _legacy_uuid("shop", client.shop_id) if client.shop_id else None,
            client.name,
            client.phone,
            _legacy_gender(client.gender),
            client.created_at,
            client.created_at,
        )


def _build_survey_rows():
    for survey in Survey.objects.order_by("id"):
        yield (
            survey.id,
            _legacy_uuid("client", survey.client_id),
            survey.target_length,
            survey.target_vibe,
            survey.scalp_type,
            survey.hair_colour,
            survey.budget_range,
            _adapt_array(survey.preference_vector or []),
            survey.created_at,
        )


def _build_analysis_rows():
    captures_by_client = _latest_capture_by_client()
    clients_by_id = {client.id: client for client in Client.objects.select_related("designer").all()}
    for analysis in FaceAnalysis.objects.order_by("id"):
        client = clients_by_id.get(analysis.client_id)
        capture = _capture_for_analysis(analysis, captures_by_client)
        face_ratio_vector = []
        if isinstance(analysis.landmark_snapshot, dict):
            ratios = analysis.landmark_snapshot.get("face_ratio_vector")
            if isinstance(ratios, list):
                face_ratio_vector = ratios
        yield (
            analysis.id,
            _legacy_uuid("client", analysis.client_id),
            (_legacy_uuid("designer", client.designer_id) if client and client.designer_id else None),
            (capture.processed_path if capture else None),
            analysis.face_shape,
            _adapt_array(face_ratio_vector),
            analysis.golden_ratio_score,
            _adapt_json(analysis.landmark_snapshot),
            analysis.created_at,
        )


def _build_result_rows_and_details():
    latest_analysis = _latest_analysis_by_client()
    latest_batches = _latest_batch_recommendations_by_client()
    latest_selection = _latest_selection_by_client()
    latest_consultation = _latest_consultation_by_client()

    result_rows = []
    detail_rows = []

    for client_id, recommendations in latest_batches.items():
        if not recommendations:
            continue

        chosen = next((row for row in recommendations if row.is_chosen), None)
        selected_row = chosen or recommendations[0]
        selection = latest_selection.get(client_id)
        consultation = latest_consultation.get(client_id)
        analysis = latest_analysis.get(client_id)

        updated_at = (
            (consultation.created_at if consultation else None)
            or (selection.created_at if selection else None)
            or selected_row.chosen_at
            or selected_row.created_at
        )

        result_rows.append(
            (
                selected_row.id,
                (analysis.id if analysis else None),
                _legacy_uuid("client", client_id),
                selected_row.style_id_snapshot,
                selected_row.simulation_image_url,
                bool(chosen or selection or consultation),
                selected_row.created_at,
                updated_at,
            )
        )

        for recommendation in recommendations:
            detail_rows.append(
                (
                    recommendation.id,
                    selected_row.id,
                    recommendation.style_id_snapshot,
                    recommendation.rank,
                    _score_or_zero(recommendation.match_score),
                    _score_or_zero(recommendation.match_score),
                    recommendation.simulation_image_url,
                    (recommendation.reasoning_snapshot or {}).get("summary") or recommendation.llm_explanation,
                )
            )

    return result_rows, detail_rows


def _build_hairstyle_rows():
    for style in Style.objects.order_by("id"):
        yield (
            style.id,
            str(style.id),
            style.name,
            style.image_url,
            style.created_at,
        )


def _clear_legacy_tables(cursor, tables: list[str]) -> None:
    for table in tables:
        cursor.execute(f"DELETE FROM {table}")


def sync_legacy_model_tables(*, strict: bool = False) -> LegacySyncSummary:
    existing_tables = _existing_legacy_tables()
    if strict and set(existing_tables) != set(LEGACY_TABLES):
        missing = sorted(set(LEGACY_TABLES) - set(existing_tables))
        raise RuntimeError(f"Missing legacy tables: {', '.join(missing)}")
    if not existing_tables:
        raise RuntimeError("No legacy model tables were found.")

    result_rows, detail_rows = _build_result_rows_and_details()

    with transaction.atomic():
        with connection.cursor() as cursor:
            _clear_legacy_tables(cursor, [table for table in LEGACY_TABLES if table in existing_tables])

            if "shop" in existing_tables:
                cursor.executemany(
                    """
                    INSERT INTO shop (
                        shop_id, login_id, shop_name, biz_number, owner_phone, password, admin_pin, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    list(_build_shop_rows()),
                )

            if "designer" in existing_tables:
                cursor.executemany(
                    """
                    INSERT INTO designer (
                        designer_id, shop_id, designer_name, login_id, password, is_active, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    list(_build_designer_rows()),
                )

            if "client" in existing_tables:
                cursor.executemany(
                    """
                    INSERT INTO client (
                        client_id, shop_id, client_name, phone, gender, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    list(_build_client_rows()),
                )

            if "client_survey" in existing_tables:
                cursor.executemany(
                    """
                    INSERT INTO client_survey (
                        survey_id, client_id, hair_length, hair_mood, hair_condition, hair_color, budget, preference_vector, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    list(_build_survey_rows()),
                )

            if "client_analysis" in existing_tables:
                cursor.executemany(
                    """
                    INSERT INTO client_analysis (
                        analysis_id, client_id, designer_id, original_image_url, face_type, face_ratio_vector, golden_ratio_score, landmark_data, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    list(_build_analysis_rows()),
                )

            if "hairstyle" in existing_tables:
                cursor.executemany(
                    """
                    INSERT INTO hairstyle (
                        hairstyle_id, chroma_id, style_name, image_url, created_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    list(_build_hairstyle_rows()),
                )

            if "client_result" in existing_tables and result_rows:
                cursor.executemany(
                    """
                    INSERT INTO client_result (
                        result_id, analysis_id, client_id, selected_hairstyle_id, selected_image_url, is_confirmed, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    result_rows,
                )

            if "client_result_detail" in existing_tables and detail_rows:
                cursor.executemany(
                    """
                    INSERT INTO client_result_detail (
                        detail_id, result_id, hairstyle_id, rank, similarity_score, final_score, simulated_image_url, recommendation_reason
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    detail_rows,
                )

    return LegacySyncSummary(
        shop_count=AdminAccount.objects.count(),
        designer_count=Designer.objects.count(),
        client_count=Client.objects.count(),
        survey_count=Survey.objects.count(),
        analysis_count=FaceAnalysis.objects.count(),
        result_count=len(result_rows),
        result_detail_count=len(detail_rows),
        hairstyle_count=Style.objects.count(),
    )


def sync_legacy_model_tables_if_present(*, strict: bool = False) -> LegacySyncSummary | None:
    if not _existing_legacy_tables():
        return None
    return sync_legacy_model_tables(strict=strict)
