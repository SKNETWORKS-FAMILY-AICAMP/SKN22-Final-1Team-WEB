import json
import logging
import os
import re
from collections import Counter
from urllib import error, request

from django.contrib.auth.hashers import check_password, make_password
from django.db.models import Count, Q
from django.utils import timezone

from app.api.v1.admin_auth import issue_admin_token_pair
from app.api.v1.recommendation_logic import STYLE_CATALOG
from app.api.v1.services_django import ensure_catalog_styles, get_latest_analysis, get_latest_survey, serialize_recommendation_row
from app.models_django import AdminAccount, CaptureRecord, ConsultationRequest, Client, ClientSessionNote, Designer, FormerRecommendation, Style, StyleSelection
from app.services.age_profile import build_client_age_profile
from app.services.ai_facade import get_ai_health
from app.services.storage_service import build_storage_snapshot, resolve_storage_reference


logger = logging.getLogger(__name__)


def _normalize_phone(value: str) -> str:
    return value.replace("-", "").strip()


def _normalize_business_number(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _format_business_number(value: str) -> str:
    return f"{value[:3]}-{value[3:5]}-{value[5:]}"


def _is_valid_business_number(value: str) -> bool:
    if len(value) != 10 or not value.isdigit():
        return False

    digits = [int(char) for char in value]
    weights = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    checksum = sum(digit * weight for digit, weight in zip(digits[:9], weights))
    checksum += (digits[8] * 5) // 10
    expected = (10 - (checksum % 10)) % 10
    return digits[9] == expected


def _business_number_variants(value: str) -> set[str]:
    normalized = _normalize_business_number(value)
    if len(normalized) != 10:
        return {value}
    return {normalized, _format_business_number(normalized)}


def _ai_health() -> dict:
    return {
        **get_ai_health(),
        "checked_at": timezone.now(),
    }


def _serialize_survey(survey) -> dict | None:
    if not survey:
        return None
    return {
        "target_length": survey.target_length,
        "target_vibe": survey.target_vibe,
        "scalp_type": survey.scalp_type,
        "hair_colour": survey.hair_colour,
        "budget_range": survey.budget_range,
        "preference_vector": survey.preference_vector or [],
        "created_at": survey.created_at,
    }


def _serialize_analysis(analysis) -> dict | None:
    if not analysis:
        return None
    return {
        "face_shape": analysis.face_shape,
        "golden_ratio_score": analysis.golden_ratio_score,
        "image_url": resolve_storage_reference(analysis.image_url),
        "landmark_snapshot": analysis.landmark_snapshot,
        "created_at": analysis.created_at,
    }


def _serialize_capture(record: CaptureRecord) -> dict:
    privacy_snapshot = record.privacy_snapshot or {}
    return {
        "record_id": record.id,
        "status": record.status,
        "face_count": record.face_count,
        "landmark_snapshot": record.landmark_snapshot,
        "deidentified_image_url": resolve_storage_reference(record.deidentified_path),
        "privacy_snapshot": privacy_snapshot,
        "image_storage_policy": privacy_snapshot.get("storage_policy", "asset_store"),
        "error_note": record.error_note,
        "original_image_url": resolve_storage_reference(record.original_path),
        "processed_image_url": resolve_storage_reference(record.processed_path),
        "storage_snapshot": build_storage_snapshot(
            original_path=record.original_path,
            processed_path=record.processed_path,
            deidentified_path=record.deidentified_path,
        ),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _style_snapshot(style_id: int) -> dict:
    styles_by_id = ensure_catalog_styles()
    style = styles_by_id.get(style_id) or Style.objects.filter(id=style_id).first()
    if not style:
        return {
            "style_id": style_id,
            "style_name": f"Style {style_id}",
            "image_url": None,
            "description": "",
            "keywords": [],
        }

    profile = next((item for item in STYLE_CATALOG if item.style_id == style_id), None)
    keywords = list(profile.keywords) if profile else ([style.vibe] if style.vibe else [])
    return {
        "style_id": style.id,
        "style_name": style.name,
        "image_url": resolve_storage_reference(style.image_url),
        "description": style.description or "",
        "keywords": keywords,
    }


def _serialize_recommendation(row: FormerRecommendation) -> dict:
    return serialize_recommendation_row(row)


def _serialize_style_selection(selection: StyleSelection) -> dict:
    style_snapshot = _style_snapshot(selection.style_id)
    return {
        "selection_id": selection.id,
        "style_id": selection.style_id,
        "style_name": style_snapshot["style_name"],
        "image_url": style_snapshot["image_url"],
        "description": style_snapshot["description"],
        "source": selection.source,
        "match_score": selection.match_score,
        "is_sent_to_admin": selection.is_sent_to_admin,
        "created_at": selection.created_at,
    }


def _serialize_admin_profile(admin: AdminAccount) -> dict:
    formatted_business_number = (
        _format_business_number(admin.business_number)
        if len(admin.business_number) == 10 and admin.business_number.isdigit()
        else admin.business_number
    )
    return {
        "admin_id": admin.id,
        "name": admin.name,
        "store_name": admin.store_name,
        "role": admin.role,
        "phone": admin.phone,
        "business_number": formatted_business_number,
        "consent_snapshot": admin.consent_snapshot or {},
        "consented_at": admin.consented_at,
        "is_active": admin.is_active,
        "created_at": admin.created_at,
    }


def _serialize_designer_profile(designer: Designer | None) -> dict | None:
    if designer is None:
        return None
    return {
        "designer_id": designer.id,
        "name": designer.name,
        "shop_id": designer.shop_id,
        "shop_name": designer.shop.store_name,
        "phone": designer.phone,
        "is_active": designer.is_active,
        "created_at": designer.created_at,
    }


def _client_age_fields(client: Client) -> dict:
    profile = build_client_age_profile(client) or {}
    return {
        "age": profile.get("current_age"),
        "age_decade": profile.get("age_decade"),
        "age_segment": profile.get("age_segment"),
        "age_group": profile.get("age_group"),
    }


def _scoped_client_queryset(*, admin: AdminAccount | None = None, designer: Designer | None = None):
    queryset = Client.objects.all()
    if designer is not None:
        return queryset.filter(designer=designer)

    if admin is None:
        return queryset

    return queryset.filter(
        Q(shop=admin)
        | Q(designer__shop=admin)
        | Q(consultations__admin=admin)
        | Q(session_notes__admin=admin)
    ).distinct()


def _scoped_consultation_queryset(*, admin: AdminAccount | None = None, designer: Designer | None = None):
    queryset = ConsultationRequest.objects.all()
    if designer is not None:
        return queryset.filter(Q(designer=designer) | Q(client__designer=designer)).distinct()

    if admin is None:
        return queryset

    return queryset.filter(
        Q(admin=admin)
        | Q(client__shop=admin)
        | Q(designer__shop=admin)
    ).distinct()


def get_admin_profile(*, admin: AdminAccount) -> dict:
    return {
        "status": "success",
        "admin": _serialize_admin_profile(admin),
    }


def register_admin(*, payload: dict) -> dict:
    phone = _normalize_phone(payload["phone"])
    business_number = _normalize_business_number(payload["business_number"])
    consent_snapshot = {
        "agree_terms": bool(payload.get("agree_terms")),
        "agree_privacy": bool(payload.get("agree_privacy")),
        "agree_third_party_sharing": bool(payload.get("agree_third_party_sharing")),
        "agree_marketing": bool(payload.get("agree_marketing", False)),
    }

    if AdminAccount.objects.filter(phone=phone).exists():
        raise ValueError("이미 등록된 관리자 연락처입니다.")
    if not _is_valid_business_number(business_number):
        raise ValueError("유효하지 않은 사업자등록번호입니다.")
    if AdminAccount.objects.filter(Q(business_number__in=_business_number_variants(business_number))).exists():
        raise ValueError("이미 등록된 사업자등록번호입니다.")

    admin = AdminAccount.objects.create(
        name=payload["name"],
        store_name=payload["store_name"],
        role=payload.get("role", "owner"),
        phone=phone,
        business_number=business_number,
        password_hash=make_password(payload["password"]),
        consent_snapshot=consent_snapshot,
        consented_at=timezone.now(),
    )
    return {
        "status": "success",
        "admin_id": admin.id,
        "admin": _serialize_admin_profile(admin),
        **issue_admin_token_pair(admin=admin),
    }


def login_admin(*, phone: str, password: str) -> dict:
    phone = _normalize_phone(phone)
    admin = AdminAccount.objects.filter(phone=phone, is_active=True).first()
    if not admin or not check_password(password, admin.password_hash):
        raise ValueError("관리자 계정 정보를 다시 확인해 주세요.")
    return {
        "status": "success",
        "admin": _serialize_admin_profile(admin),
        **issue_admin_token_pair(admin=admin),
    }


def _today_client_ids(*, admin: AdminAccount | None = None, designer: Designer | None = None) -> set[int]:
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    clients = _scoped_client_queryset(admin=admin, designer=designer)
    capture_ids = set(clients.filter(captures__created_at__gte=start).values_list("id", flat=True))
    consult_ids = set(clients.filter(consultations__created_at__gte=start).values_list("id", flat=True))
    return capture_ids | consult_ids


def _latest_active_consultations(*, admin: AdminAccount | None = None, designer: Designer | None = None) -> list[ConsultationRequest]:
    rows = _scoped_consultation_queryset(admin=admin, designer=designer).filter(is_active=True).select_related("client", "selected_style", "selected_recommendation", "designer").order_by("-created_at")
    seen: set[int] = set()
    latest_rows: list[ConsultationRequest] = []
    for row in rows:
        if row.client_id in seen:
            continue
        seen.add(row.client_id)
        latest_rows.append(row)
    return latest_rows


def get_admin_dashboard_summary(*, admin: AdminAccount | None = None, designer: Designer | None = None) -> dict:
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    styles_by_id = ensure_catalog_styles()
    style_selection_queryset = StyleSelection.objects.filter(created_at__gte=start)
    scoped_clients = _scoped_client_queryset(admin=admin, designer=designer).values_list("id", flat=True)
    style_selection_queryset = style_selection_queryset.filter(client_id__in=scoped_clients)
    top_rows = (
        style_selection_queryset
        .values("style_id")
        .annotate(selection_count=Count("id"))
        .order_by("-selection_count", "style_id")[:5]
    )
    top_styles = []
    for row in top_rows:
        style = styles_by_id.get(row["style_id"]) or Style.objects.filter(id=row["style_id"]).first()
        top_styles.append(
            {
                "style_id": row["style_id"],
                "style_name": style.name if style else f"Style {row['style_id']}",
                "image_url": resolve_storage_reference(style.image_url) if style else None,
                "selection_count": row["selection_count"],
            }
        )

    active_consultations = _latest_active_consultations(admin=admin, designer=designer)
    active_preview = [
        {
            "consultation_id": row.id,
            "client_id": row.client_id,
            "client_name": row.client.name,
            "phone": row.client.phone,
            "has_unread_consultation": not row.is_read,
            "status": row.status,
            "selected_style_name": row.selected_style.name if row.selected_style else None,
            "created_at": row.created_at,
        }
        for row in active_consultations[:5]
    ]
    return {
        "status": "ready",
        "ai_engine": _ai_health(),
        "today_metrics": {
            "unique_visitors": len(_today_client_ids(admin=admin, designer=designer)),
            "active_clients": len(active_consultations),
            "pending_consultations": sum(1 for row in active_consultations if not row.is_read),
            "confirmed_styles": style_selection_queryset.count(),
        },
        "top_styles_today": top_styles,
        "active_clients_preview": active_preview,
    }


def get_active_client_sessions(*, admin: AdminAccount | None = None, designer: Designer | None = None) -> dict:
    items = []
    for row in _latest_active_consultations(admin=admin, designer=designer):
        recommendation_count = 0
        if row.selected_recommendation:
            recommendation_count = FormerRecommendation.objects.filter(
                client_id=row.client_id,
                batch_id=row.selected_recommendation.batch_id,
            ).count()
        items.append(
            {
                "consultation_id": row.id,
                "client_id": row.client_id,
                "client_name": row.client.name,
                "phone": row.client.phone,
                "status": row.status,
                "has_unread_consultation": not row.is_read,
                "designer_id": row.designer_id or row.client.designer_id,
                "designer_name": (
                    row.designer.name
                    if row.designer_id and row.designer
                    else (row.client.designer.name if row.client.designer_id else None)
                ),
                "selected_style_name": row.selected_style.name if row.selected_style else None,
                "recommendation_count": recommendation_count,
                "last_activity_at": row.created_at,
            }
        )
    return {"status": "ready", "items": items}


def get_all_clients(*, query: str = "", admin: AdminAccount | None = None, designer: Designer | None = None) -> dict:
    queryset = _scoped_client_queryset(admin=admin, designer=designer).select_related("shop", "designer").order_by("name", "id")
    if query:
        queryset = queryset.filter(Q(name__icontains=query) | Q(phone__icontains=query))

    items = []
    for client in queryset[:100]:
        latest_consult = client.consultations.order_by("-created_at").first()
        items.append(
            {
                "client_id": client.id,
                "name": client.name,
                "gender": client.gender,
                "phone": client.phone,
                "shop_id": client.shop_id,
                "shop_name": client.shop.store_name if client.shop_id and client.shop else None,
                "designer_id": client.designer_id,
                "designer_name": client.designer.name if client.designer_id and client.designer else None,
                "assigned_at": client.assigned_at,
                "assignment_source": client.assignment_source,
                "is_assignment_pending": client.designer_id is None and bool(client.shop_id),
                **_client_age_fields(client),
                "created_at": client.created_at,
                "last_consulted_at": latest_consult.created_at if latest_consult else None,
                "has_active_consultation": client.consultations.filter(is_active=True).exists(),
            }
        )
    return {"status": "ready", "items": items}


def assign_client_to_designer(
    *,
    client: Client,
    designer_id: int,
    admin: AdminAccount,
) -> dict:
    designer = (
        Designer.objects.filter(
            id=designer_id,
            shop=admin,
            is_active=True,
        )
        .select_related("shop")
        .first()
    )
    if designer is None:
        raise ValueError("해당 매장 소속의 활성 디자이너를 찾을 수 없습니다.")

    if client.shop_id not in (None, admin.id) and client.designer_id is None:
        raise ValueError("현재 매장 범위를 벗어난 고객입니다.")

    if client.shop_id is None:
        client.shop = admin

    client.designer = designer
    client.assigned_at = timezone.now()
    client.assignment_source = "shop_manual_assignment"
    client.save(update_fields=["shop", "designer", "assigned_at", "assignment_source"])

    return {
        "status": "success",
        "client_id": client.id,
        "designer_id": designer.id,
        "designer_name": designer.name,
        "assigned_at": client.assigned_at,
        "assignment_source": client.assignment_source,
    }


def get_client_detail(*, client: Client, admin: AdminAccount | None = None, designer: Designer | None = None) -> dict:
    scoped_client_ids = set(_scoped_client_queryset(admin=admin, designer=designer).values_list("id", flat=True))
    if scoped_client_ids and client.id not in scoped_client_ids:
        raise ValueError("Client is outside the current admin scope.")

    latest_survey = get_latest_survey(client)
    latest_analysis = get_latest_analysis(client)
    consultation_queryset = client.consultations
    if designer is not None:
        consultation_queryset = consultation_queryset.filter(Q(designer=designer) | Q(client__designer=designer))
    elif admin is not None and scoped_client_ids:
        consultation_queryset = consultation_queryset.filter(Q(admin=admin) | Q(client__shop=admin) | Q(designer__shop=admin))
    latest_consultation = consultation_queryset.select_related("designer").order_by("-created_at").first()
    notes_queryset = ClientSessionNote.objects.filter(client=client).select_related("admin", "designer", "consultation")
    if designer is not None:
        notes_queryset = notes_queryset.filter(Q(designer=designer) | Q(client__designer=designer))
    elif admin is not None and scoped_client_ids:
        notes_queryset = notes_queryset.filter(Q(admin=admin) | Q(client__shop=admin) | Q(designer__shop=admin))
    notes = notes_queryset.order_by("-created_at")[:20]
    capture_history = client.captures.order_by("-created_at")[:20]
    analysis_history = client.face_analyses.order_by("-created_at")[:20]
    selection_history = client.style_selections.order_by("-created_at")[:20]
    chosen_recommendations = FormerRecommendation.objects.filter(client=client, is_chosen=True).order_by("-chosen_at", "-created_at")[:20]

    return {
        "status": "ready",
        "client": {
            "client_id": client.id,
            "name": client.name,
            "gender": client.gender,
            "phone": client.phone,
            "shop_id": client.shop_id,
            "shop_name": client.shop.store_name if client.shop_id and client.shop else None,
            "designer": _serialize_designer_profile(client.designer),
            **_client_age_fields(client),
            "created_at": client.created_at,
        },
        "latest_survey": _serialize_survey(latest_survey),
        "latest_analysis": _serialize_analysis(latest_analysis),
        "capture_history": [_serialize_capture(record) for record in capture_history],
        "analysis_history": [_serialize_analysis(analysis) for analysis in analysis_history],
        "style_selection_history": [_serialize_style_selection(selection) for selection in selection_history],
        "chosen_recommendation_history": [_serialize_recommendation(row) for row in chosen_recommendations],
        "active_consultation": (
            {
                "consultation_id": latest_consultation.id,
                "status": latest_consultation.status,
                "is_active": latest_consultation.is_active,
                "is_read": latest_consultation.is_read,
                "source": latest_consultation.source,
                "designer_id": latest_consultation.designer_id,
                "designer_name": latest_consultation.designer.name if latest_consultation.designer_id and latest_consultation.designer else None,
                "created_at": latest_consultation.created_at,
                "closed_at": latest_consultation.closed_at,
            }
            if latest_consultation
            else None
        ),
        "notes": [
            {
                "note_id": note.id,
                "consultation_id": note.consultation_id,
                "admin_id": note.admin_id,
                "admin_name": note.admin.name if note.admin else None,
                "designer_id": note.designer_id,
                "designer_name": note.designer.name if note.designer else None,
                "content": note.content,
                "created_at": note.created_at,
            }
            for note in notes
        ],
    }


def get_client_recommendation_report(*, client: Client, admin: AdminAccount | None = None, designer: Designer | None = None) -> dict:
    scoped_client_ids = set(_scoped_client_queryset(admin=admin, designer=designer).values_list("id", flat=True))
    if scoped_client_ids and client.id not in scoped_client_ids:
        raise ValueError("Client is outside the current admin scope.")

    latest_analysis = get_latest_analysis(client)
    latest_survey = get_latest_survey(client)
    recommendation_queryset = FormerRecommendation.objects.filter(client=client, source="generated")
    if (admin is not None or designer is not None) and scoped_client_ids:
        recommendation_queryset = recommendation_queryset.filter(client_id__in=scoped_client_ids)
    latest_generated = recommendation_queryset.order_by("-created_at").first()
    batch_rows = []
    if latest_generated:
        batch_rows = list(FormerRecommendation.objects.filter(client=client, batch_id=latest_generated.batch_id).order_by("rank", "id"))
    final_selected = FormerRecommendation.objects.filter(client=client, is_chosen=True).order_by("-chosen_at", "-created_at").first()

    return {
        "status": "ready",
        "client": {
            "client_id": client.id,
            "name": client.name,
            "phone": client.phone,
            **_client_age_fields(client),
        },
        "latest_survey": _serialize_survey(latest_survey),
        "latest_analysis": _serialize_analysis(latest_analysis),
        "final_selected_style": (_serialize_recommendation(final_selected) if final_selected else None),
        "latest_generated_batch": {
            "batch_id": str(latest_generated.batch_id) if latest_generated else None,
            "items": [_serialize_recommendation(row) for row in batch_rows],
        },
    }


def create_client_note(*, client: Client, consultation_id: int, content: str, admin: AdminAccount | None = None, designer: Designer | None = None) -> dict:
    consultation = ConsultationRequest.objects.filter(id=consultation_id, client=client).first()
    if not consultation:
        raise ValueError("The consultation session could not be found.")

    if admin is not None and consultation.admin_id is None:
        consultation.admin = admin
    if designer is not None and consultation.designer_id is None:
        consultation.designer = designer
    if admin is not None or designer is not None:
        update_fields = []
        if admin is not None and consultation.admin_id == admin.id:
            update_fields.append("admin")
        if designer is not None and consultation.designer_id == designer.id:
            update_fields.append("designer")
        if update_fields:
            consultation.save(update_fields=update_fields)

    note = ClientSessionNote.objects.create(
        consultation=consultation,
        client=client,
        admin=admin,
        designer=designer,
        content=content.strip(),
    )
    consultation.is_read = True
    consultation.status = "IN_PROGRESS"
    consultation.save(update_fields=["is_read", "status"])
    return {
        "status": "success",
        "note_id": note.id,
        "consultation_id": consultation.id,
        "message": "The consultation note has been saved.",
    }


def close_consultation_session(*, consultation_id: int, admin: AdminAccount | None = None, designer: Designer | None = None) -> dict:
    consultation = ConsultationRequest.objects.filter(id=consultation_id).select_related("client").first()
    if not consultation:
        raise ValueError("The consultation session could not be found.")

    if admin is not None and consultation.admin_id is None:
        consultation.admin = admin
    if designer is not None and consultation.designer_id is None:
        consultation.designer = designer

    consultation.is_active = False
    consultation.is_read = True
    consultation.status = "CLOSED"
    consultation.closed_at = timezone.now()
    update_fields = ["is_active", "is_read", "status", "closed_at"]
    if admin is not None and consultation.admin_id == admin.id:
        update_fields.append("admin")
    if designer is not None and consultation.designer_id == designer.id:
        update_fields.append("designer")
    consultation.save(update_fields=update_fields)
    return {
        "status": "success",
        "consultation_id": consultation.id,
        "client_id": consultation.client_id,
        "message": "The consultation session has been closed.",
    }


def _selection_matches_snapshot(selection: StyleSelection, filters: dict) -> bool:
    snapshot = selection.survey_snapshot or {}
    if not snapshot and hasattr(selection.client, "survey"):
        survey = selection.client.survey
        snapshot = {
            "target_length": survey.target_length,
            "target_vibe": survey.target_vibe,
            "scalp_type": survey.scalp_type,
            "hair_colour": survey.hair_colour,
            "budget_range": survey.budget_range,
        }
    age_profile = build_client_age_profile(selection.client) or snapshot.get("age_profile") or {}

    for key, value in filters.items():
        if value in (None, ""):
            continue
        if key == "age_decade":
            if age_profile.get("age_decade") != value:
                return False
            continue
        if key == "age_segment":
            if age_profile.get("age_segment") != value:
                return False
            continue
        if key == "age_group":
            if age_profile.get("age_group") != value:
                return False
            continue
        if snapshot.get(key) != value:
            return False
    return True


def _build_trend_report_snapshot(*, days: int, filters: dict, admin: AdminAccount | None, designer: Designer | None, total_records: int, filtered_records: int, ranking_count: int, unique_clients: int) -> dict:
    return {
        "days": days,
        "filters": filters,
        "admin_scoped": admin is not None,
        "designer_scoped": designer is not None,
        "total_records": total_records,
        "filtered_records": filtered_records,
        "ranking_count": ranking_count,
        "unique_clients": unique_clients,
    }


def _build_style_report_snapshot(*, style_id: int, days: int, admin: AdminAccount | None, designer: Designer | None, recent_count: int, chosen_count: int, related_count: int) -> dict:
    return {
        "style_id": style_id,
        "days": days,
        "admin_scoped": admin is not None,
        "designer_scoped": designer is not None,
        "recent_selection_count": recent_count,
        "chosen_count": chosen_count,
        "related_style_count": related_count,
    }


def get_admin_trend_report(*, days: int = 7, filters: dict | None = None, admin: AdminAccount | None = None, designer: Designer | None = None) -> dict:
    filters = filters or {}
    cutoff = timezone.now() - timezone.timedelta(days=days)
    selections_queryset = StyleSelection.objects.filter(created_at__gte=cutoff).select_related("client").order_by("-created_at")
    scoped_client_ids = list(_scoped_client_queryset(admin=admin, designer=designer).values_list("id", flat=True))
    if admin is not None or designer is not None:
        selections_queryset = selections_queryset.filter(client_id__in=scoped_client_ids)
    selections = list(selections_queryset)
    filtered = [row for row in selections if _selection_matches_snapshot(row, filters)]

    counter = Counter(row.style_id for row in filtered)
    ranking = []
    for rank, (style_id, count) in enumerate(counter.most_common(10), start=1):
        style_data = _style_snapshot(style_id)
        ranking.append(
            {
                "rank": rank,
                "style_id": style_id,
                "style_name": style_data["style_name"],
                "image_url": style_data["image_url"],
                "selection_count": count,
                "keywords": style_data["keywords"],
            }
        )

    distribution = [
        {
            "style_id": item["style_id"],
            "style_name": item["style_name"],
            "selection_count": item["selection_count"],
        }
        for item in ranking
    ]
    age_decade_counter = Counter()
    age_group_counter = Counter()
    for row in filtered:
        profile = build_client_age_profile(row.client)
        if not profile:
            continue
        if profile.get("age_decade"):
            age_decade_counter[profile["age_decade"]] += 1
        if profile.get("age_group"):
            age_group_counter[profile["age_group"]] += 1
    unique_clients = len({row.client_id for row in filtered})
    report_snapshot = _build_trend_report_snapshot(
        days=days,
        filters=filters,
        admin=admin,
        designer=designer,
        total_records=len(selections),
        filtered_records=len(filtered),
        ranking_count=len(ranking),
        unique_clients=unique_clients,
    )
    logger.info(
        "[trend_report] days=%s total=%s filtered=%s ranking=%s admin_scoped=%s designer_scoped=%s",
        days,
        len(selections),
        len(filtered),
        len(ranking),
        admin is not None,
        designer is not None,
    )
    return {
        "status": "ready",
        "days": days,
        "filters": filters,
        "kpi": {
            "unique_clients": unique_clients,
            "total_confirmations": len(filtered),
            "active_consultations": len(_latest_active_consultations(admin=admin, designer=designer)),
        },
        "ranking": ranking,
        "distribution": distribution,
        "age_decade_distribution": [
            {"age_decade": key, "selection_count": count}
            for key, count in age_decade_counter.most_common()
        ],
        "age_group_distribution": [
            {"age_group": key, "selection_count": count}
            for key, count in age_group_counter.most_common()
        ],
        "report_snapshot": report_snapshot,
        "message": (
            "Trend report generated successfully."
            if filtered
            else "No trend selections were found for the requested period."
        ),
    }


def get_style_report(*, style_id: int, days: int = 7, admin: AdminAccount | None = None, designer: Designer | None = None) -> dict:
    style_data = _style_snapshot(style_id)
    cutoff = timezone.now() - timezone.timedelta(days=days)
    recent_queryset = StyleSelection.objects.filter(style_id=style_id, created_at__gte=cutoff)
    chosen_queryset = FormerRecommendation.objects.filter(style_id_snapshot=style_id, is_chosen=True)
    scoped_client_ids = list(_scoped_client_queryset(admin=admin, designer=designer).values_list("id", flat=True))
    if admin is not None or designer is not None:
        recent_queryset = recent_queryset.filter(client_id__in=scoped_client_ids)
        chosen_queryset = chosen_queryset.filter(client_id__in=scoped_client_ids)
    recent_count = recent_queryset.count()
    chosen_count = chosen_queryset.count()

    related = []
    target_profile = next((item for item in STYLE_CATALOG if item.style_id == style_id), None)
    if target_profile:
        scored = []
        for profile in STYLE_CATALOG:
            if profile.style_id == style_id:
                continue
            score = len(set(target_profile.keywords) & set(profile.keywords))
            if set(target_profile.vibe_tags) & set(profile.vibe_tags):
                score += 1
            scored.append((score, profile.style_id))
        for _, related_style_id in sorted(scored, key=lambda item: (-item[0], item[1]))[:5]:
            related.append(_style_snapshot(related_style_id))

    report_snapshot = _build_style_report_snapshot(
        style_id=style_id,
        days=days,
        admin=admin,
        designer=designer,
        recent_count=recent_count,
        chosen_count=chosen_count,
        related_count=len(related),
    )
    logger.info(
        "[style_report] style_id=%s days=%s recent=%s chosen=%s related=%s admin_scoped=%s designer_scoped=%s",
        style_id,
        days,
        recent_count,
        chosen_count,
        len(related),
        admin is not None,
        designer is not None,
    )
    return {
        "status": "ready",
        "style": {
            **style_data,
            "recent_selection_count": recent_count,
            "chosen_count": chosen_count,
        },
        "related_styles": related,
        "report_snapshot": report_snapshot,
    }

