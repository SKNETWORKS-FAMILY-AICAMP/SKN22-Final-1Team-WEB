import io
import json
import threading
import logging

from django.conf import settings
from django.http import Http404
from PIL import Image, ImageOps
from rest_framework import parsers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema

from app.api.v1.admin_auth import issue_client_token_pair, refresh_client_access_token
from app.api.v1.response_helpers import CompatEnvelopeAPIView, detail_response
from app.api.v1.django_serializers import (
    ClientCheckSerializer,
    ClientRegisterSerializer,
    RegenerateSimulationRequestSerializer,
    RecommendationListResponseSerializer,
    RetryRecommendationRequestSerializer,
    SurveySerializer,
    TokenRefreshSerializer,
)
from app.api.v1.services_django import (
    cancel_style_selection,
    confirm_style_selection,
    get_current_recommendations,
    get_former_recommendations,
    get_latest_capture,
    get_trend_recommendations,
    regenerate_recommendation_simulation,
    retry_current_recommendations,
    run_hairstyle_generation_pipeline,
    run_mirrai_analysis_pipeline,
    serialize_capture_status,
    upsert_survey,
)
from app.services.age_profile import build_client_age_profile
from app.services.capture_validation import (
    build_capture_validation_snapshot,
    sanitize_original_upload,
    validate_capture_image,
)
from app.services.face_processing import build_deidentified_capture, extract_landmark_snapshot
from app.services.model_team_bridge import (
    create_legacy_capture_upload_record,
    get_client_by_identifier,
    get_client_by_phone,
    get_legacy_capture_by_identifier,
    get_legacy_client_id,
    upsert_client_record,
)
from app.services.storage_service import build_storage_snapshot, store_capture_assets


logger = logging.getLogger(__name__)


def _request_value(request, *keys: str):
    for key in keys:
        value = request.data.get(key)
        if value not in (None, ""):
            return value
    return None


def _query_value(request, *keys: str):
    for key in keys:
        value = request.query_params.get(key)
        if value not in (None, ""):
            return value
    return None


def _get_client_or_404(identifier):
    client = get_client_by_identifier(identifier=identifier)
    if client is None:
        raise Http404("Client not found.")
    return client


def _parse_front_capture_context(request) -> dict | None:
    raw_value = request.data.get("front_capture_context")
    if raw_value in (None, ""):
        return None
    if isinstance(raw_value, dict):
        return raw_value
    if not isinstance(raw_value, str):
        return None
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        logger.warning("[capture_upload_front_context_invalid] payload_type=%s", type(raw_value).__name__)
        return None
    return parsed if isinstance(parsed, dict) else None


class LoginView(CompatEnvelopeAPIView):
    @extend_schema(
        summary="Log in client",
        request={
            "application/json": {
                "type": "object",
                "properties": {"phone": {"type": "string", "example": "010-9999-8888"}},
            }
        },
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        phone = request.data.get("phone", "").replace("-", "").strip()
        if not phone:
            return detail_response("Phone number is required.", status_code=status.HTTP_400_BAD_REQUEST)

        client = get_client_by_phone(phone=phone)
        if not client:
            return detail_response("Client not found.", status_code=status.HTTP_404_NOT_FOUND)

        age_profile = build_client_age_profile(client) or {}
        return Response(
            {
                "client_id": client.id,
                "legacy_client_id": get_legacy_client_id(client=client),
                "age": age_profile.get("current_age"),
                "age_decade": age_profile.get("age_decade"),
                "age_segment": age_profile.get("age_segment"),
                "age_group": age_profile.get("age_group"),
                **issue_client_token_pair(client=client),
            }
        )


class ClientRefreshView(CompatEnvelopeAPIView):
    @extend_schema(summary="Refresh client token", request=TokenRefreshSerializer, responses={200: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT})
    def post(self, request):
        serializer = TokenRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = refresh_client_access_token(refresh_token=serializer.validated_data["refresh_token"])
        except Exception as exc:
            logger.warning("[client_refresh_failed] reason=%s", exc)
            return detail_response(str(exc), status_code=status.HTTP_401_UNAUTHORIZED)
        return Response(payload)


class ClientCheckView(CompatEnvelopeAPIView):
    @extend_schema(summary="Check existing client", request=ClientCheckSerializer, responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        phone = request.data.get("phone", "").replace("-", "").strip()
        client = get_client_by_phone(phone=phone)
        if not client:
            return Response({"is_existing": False})

        age_profile = build_client_age_profile(client) or {}
        return Response(
            {
                "is_existing": True,
                "name": client.name,
                "gender": client.gender,
                "client_id": client.id,
                "legacy_client_id": get_legacy_client_id(client=client),
                "age": age_profile.get("current_age"),
                "age_decade": age_profile.get("age_decade"),
                "age_segment": age_profile.get("age_segment"),
                "age_group": age_profile.get("age_group"),
            }
        )


class RegisterView(CompatEnvelopeAPIView):
    @extend_schema(summary="Register new client", request=ClientRegisterSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        phone = request.data.get("phone", "").replace("-", "").strip()
        if get_client_by_phone(phone=phone) is not None:
            return detail_response(
                "This phone number is already registered.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ClientRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client = upsert_client_record(
            phone=phone,
            name=serializer.validated_data["name"],
            gender=serializer.validated_data.get("gender"),
            age_input=serializer.validated_data.get("age_input"),
            birth_year_estimate=serializer.validated_data.get("birth_year_estimate"),
        )

        age_profile = build_client_age_profile(client) or {}
        return Response(
            {
                "status": "success",
                "client_id": client.id,
                "legacy_client_id": get_legacy_client_id(client=client),
                "age": age_profile.get("current_age"),
                "age_decade": age_profile.get("age_decade"),
                "age_segment": age_profile.get("age_segment"),
                "age_group": age_profile.get("age_group"),
                **issue_client_token_pair(client=client),
            },
            status=status.HTTP_201_CREATED,
        )


class SurveyView(CompatEnvelopeAPIView):
    @extend_schema(summary="Submit client survey", request=SurveySerializer, responses={200: SurveySerializer})
    def post(self, request):
        client_id = _request_value(request, "client", "client_id", "customer_id", "customer")
        client = _get_client_or_404(client_id)
        survey = upsert_survey(client, request.data)
        logger.info("[survey_saved] client_id=%s survey_id=%s", client.id, survey.id)

        # Phase 2: 비동기 — 백그라운드에서 헤어스타일 생성
        thread = threading.Thread(
            target=run_hairstyle_generation_pipeline,
            args=(client, survey),
            daemon=True,
        )
        thread.start()
        logger.info("[survey_saved] hairstyle pipeline started. client_id=%s", client.id)

        return Response(SurveySerializer(survey).data)


class CaptureUploadView(CompatEnvelopeAPIView):
    parser_classes = (parsers.MultiPartParser, parsers.FormParser)

    @extend_schema(
        summary="Upload client capture",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "string"},
                    "customer_id": {"type": "string"},
                    "customer": {"type": "string"},
                    "front_capture_context": {"type": "string"},
                    "file": {"type": "string", "format": "binary"},
                },
                "required": ["client_id", "file"],
            }
        },
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        client_id = _request_value(request, "client_id", "customer_id", "customer")
        client = _get_client_or_404(client_id)
        file_obj = request.FILES.get("file")
        if not file_obj:
            return detail_response("Image file is required.", status_code=status.HTTP_400_BAD_REQUEST)

        original_bytes = file_obj.read()
        original_ext = "." + file_obj.name.split(".")[-1] if "." in file_obj.name else ".jpg"
        try:
            with Image.open(io.BytesIO(original_bytes)) as image:
                image = ImageOps.exif_transpose(image)
                sanitized_original_bytes, sanitized_ext = sanitize_original_upload(
                    image=image,
                    original_ext=original_ext,
                )
                processed_buffer = io.BytesIO()
                image.convert("RGB").save(processed_buffer, "JPEG")
                processed_bytes = processed_buffer.getvalue()
        except OSError:
            return detail_response("Unsupported or invalid image file.", status_code=status.HTTP_400_BAD_REQUEST)

        validation = validate_capture_image(processed_bytes=processed_bytes)
        landmark_snapshot = extract_landmark_snapshot(processed_bytes=processed_bytes)
        front_capture_context = _parse_front_capture_context(request)
        capture_validation_snapshot = build_capture_validation_snapshot(
            validation=validation,
            landmark_snapshot=landmark_snapshot,
            front_capture_context=front_capture_context,
        )
        if settings.MIRRAI_PERSIST_CAPTURE_IMAGES:
            deidentified_bytes, privacy_snapshot = build_deidentified_capture(
                processed_bytes=processed_bytes,
                landmark_snapshot=landmark_snapshot,
            )
            stored_filename, original_path, processed_path, deidentified_path = store_capture_assets(
                original_name=file_obj.name,
                original_bytes=sanitized_original_bytes,
                processed_bytes=processed_bytes,
                original_ext=sanitized_ext,
                deidentified_bytes=deidentified_bytes,
            )
            privacy_snapshot = {
                **privacy_snapshot,
                "storage_policy": "asset_store",
            }
        else:
            stored_filename = None
            original_path = None
            processed_path = None
            deidentified_path = None
            privacy_snapshot = {
                "metadata_removed": True,
                "deidentification_applied": False,
                "storage_policy": "vector_only",
                "persisted_assets": [],
                "reason": "capture_images_not_persisted",
            }

        privacy_snapshot = {
            **privacy_snapshot,
            "capture_validation": capture_validation_snapshot,
        }

        record = create_legacy_capture_upload_record(
            client=client,
            original_path=original_path,
            processed_path=processed_path,
            filename=stored_filename,
            status=validation["status"],
            face_count=validation["face_count"],
            landmark_snapshot=landmark_snapshot,
            deidentified_path=deidentified_path,
            privacy_snapshot=privacy_snapshot,
            error_note=(None if validation["is_valid"] else validation["message"]),
        )

        storage_snapshot = build_storage_snapshot(
            original_path=original_path,
            processed_path=processed_path,
            deidentified_path=deidentified_path,
        )

        logger.info(
            (
                "[capture_upload] client_id=%s status=%s reason=%s face_count=%s "
                "storage_mode=%s has_required_assets=%s"
            ),
            client.id,
            validation["status"],
            validation["reason_code"],
            validation["face_count"],
            storage_snapshot["storage_mode"],
            storage_snapshot["has_required_capture_assets"],
        )
        logger.info(
            (
                "[capture_upload_validation] client_id=%s brightness=%s sharpness=%s "
                "face_area_ratio=%s thresholds=%s"
            ),
            client.id,
            capture_validation_snapshot["diagnostics"].get("brightness"),
            capture_validation_snapshot["diagnostics"].get("sharpness"),
            capture_validation_snapshot["diagnostics"].get("face_area_ratio"),
            capture_validation_snapshot["thresholds"],
        )
        if capture_validation_snapshot["front_capture_context_present"]:
            logger.info(
                (
                    "[capture_upload_compare] client_id=%s front_all_valid=%s front_message_key=%s "
                    "front_summary=%s backend_reason=%s backend_failed_after_front_ready=%s"
                ),
                client.id,
                capture_validation_snapshot["front_all_valid"],
                capture_validation_snapshot["front_message_key"],
                capture_validation_snapshot["front_checklist_summary"],
                capture_validation_snapshot["reason_code"],
                capture_validation_snapshot["backend_failed_after_front_ready"],
            )

        if not validation["is_valid"]:
            logger.warning(
                (
                    "[capture_upload_failed] client_id=%s record_id=%s reason=%s face_count=%s "
                    "landmark_face_count=%s brightness=%s sharpness=%s"
                ),
                client.id,
                record.id,
                validation["reason_code"],
                validation["face_count"],
                capture_validation_snapshot["landmark_face_count"],
                capture_validation_snapshot["diagnostics"].get("brightness"),
                capture_validation_snapshot["diagnostics"].get("sharpness"),
            )
            return Response(
                {
                    "status": "needs_retake",
                    "record_id": record.id,
                    "face_count": validation["face_count"],
                    "reason_code": validation["reason_code"],
                    "message": validation["message"],
                    "next_action": "capture",
                    "privacy_snapshot": privacy_snapshot,
                    "storage_snapshot": storage_snapshot,
                }
            )

        thread_args = (record.id,)
        thread_kwargs = {}
        if not settings.MIRRAI_PERSIST_CAPTURE_IMAGES:
            thread_kwargs["processed_bytes"] = processed_bytes
        threading.Thread(
            target=run_mirrai_analysis_pipeline,
            args=thread_args,
            kwargs=thread_kwargs,
            daemon=True,
        ).start()
        return Response(
            {
                "status": "success",
                "record_id": record.id,
                "face_count": validation["face_count"],
                "message": validation["message"],
                "next_action": "survey",
                "next_actions": ["survey", "result"],
                "privacy_snapshot": privacy_snapshot,
                "storage_snapshot": storage_snapshot,
            }
        )


class CaptureStatusView(CompatEnvelopeAPIView):
    @extend_schema(
        summary="Get capture processing status",
        parameters=[
            OpenApiParameter("record_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("client_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("customer_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("customer", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        record = None
        record_id = request.query_params.get("record_id")
        if record_id not in (None, ""):
            record = get_legacy_capture_by_identifier(identifier=record_id)

        if record is None:
            client_id = _query_value(request, "client_id", "customer_id", "customer")
            if client_id in (None, ""):
                return detail_response("record_id or client_id is required.", status_code=status.HTTP_400_BAD_REQUEST)
            client = _get_client_or_404(client_id)
            record = get_latest_capture(client)
            if record is None:
                raise Http404("Capture record not found.")

        payload = serialize_capture_status(record)
        logger.info(
            "[capture_status] record_id=%s status=%s storage_mode=%s",
            record.id,
            payload["status"],
            payload["storage_snapshot"]["storage_mode"],
        )
        return Response(payload)


class FormerRecommendationView(CompatEnvelopeAPIView):
    @extend_schema(
        summary="Get former recommendation history",
        parameters=[OpenApiParameter("client_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True)],
        responses={200: RecommendationListResponseSerializer},
    )
    def get(self, request):
        client_id = _query_value(request, "client_id")
        if not client_id:
            return detail_response("client_id is required.", status_code=status.HTTP_400_BAD_REQUEST)
        client = _get_client_or_404(client_id)
        payload = get_former_recommendations(client)
        return Response(payload)


class RecommendationView(CompatEnvelopeAPIView):
    @extend_schema(
        summary="Get current recommendations",
        parameters=[OpenApiParameter("client_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True)],
        responses={200: RecommendationListResponseSerializer},
    )
    def get(self, request):
        client_id = _query_value(request, "client_id")
        if not client_id:
            return detail_response("client_id is required.", status_code=status.HTTP_400_BAD_REQUEST)
        client = _get_client_or_404(client_id)
        payload = get_current_recommendations(client)
        logger.info(
            "[current_recommendations] client_id=%s item_count=%s stage=%s",
            client.id,
            len(payload.get("items", [])),
            payload.get("recommendation_stage"),
        )
        return Response(payload)


class TrendView(CompatEnvelopeAPIView):
    @extend_schema(
        summary="Get trend-based style recommendations",
        parameters=[
            OpenApiParameter("days", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("client_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: RecommendationListResponseSerializer},
    )
    def get(self, request):
        days = int(request.query_params.get("days", 30))
        client_id = _query_value(request, "client_id", "customer_id", "customer")
        client = _get_client_or_404(client_id) if client_id else None
        payload = get_trend_recommendations(days=days, client=client)
        logger.info(
            "[trend_recommendations] client_id=%s days=%s item_count=%s scope=%s",
            (client.id if client else None),
            days,
            len(payload.get("items", [])),
            payload.get("trend_scope"),
        )
        return Response(payload)


class RegenerateSimulationView(CompatEnvelopeAPIView):
    @extend_schema(
        summary="Regenerate simulation payload from vector-only snapshot",
        request=RegenerateSimulationRequestSerializer,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        serializer = RegenerateSimulationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = regenerate_recommendation_simulation(**serializer.validated_data)
        except ValueError as exc:
            return detail_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


class RetryRecommendationView(CompatEnvelopeAPIView):
    @extend_schema(
        summary="Retry the current recommendation batch once with preference-first scoring",
        request=RetryRecommendationRequestSerializer,
        responses={200: RecommendationListResponseSerializer, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        serializer = RetryRecommendationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        logger.info(
            "[retry_recommendations_request] payload_keys=%s raw_client_id=%s raw_customer_id=%s raw_customer=%s",
            sorted(request.data.keys()),
            request.data.get("client_id"),
            request.data.get("customer_id"),
            request.data.get("customer"),
        )
        client_id = (
            serializer.validated_data.get("client_id")
            or serializer.validated_data.get("customer_id")
            or serializer.validated_data.get("customer")
        )
        if not client_id:
            logger.warning(
                "[retry_recommendations_missing_client_id] payload=%s validated=%s",
                dict(request.data),
                dict(serializer.validated_data),
            )
            return detail_response("client_id is required.", status_code=status.HTTP_400_BAD_REQUEST)
        client = _get_client_or_404(client_id)
        try:
            payload = retry_current_recommendations(client)
        except ValueError as exc:
            return detail_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


class SelectionView(CompatEnvelopeAPIView):
    @extend_schema(
        summary="Legacy selection staging endpoint",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "string"},
                    "customer_id": {"type": "string"},
                    "style_id": {"type": "integer"},
                },
                "required": ["style_id"],
            }
        },
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        logger.info(
            "[selection_request] payload_keys=%s raw_client_id=%s raw_customer_id=%s raw_customer=%s raw_style_id=%s",
            sorted(request.data.keys()),
            request.data.get("client_id"),
            request.data.get("customer_id"),
            request.data.get("customer"),
            request.data.get("style_id"),
        )
        client_id = _request_value(request, "client_id", "customer_id", "customer")
        style_id = _request_value(request, "style_id")
        if not client_id or not style_id:
            logger.warning(
                "[selection_missing_required_fields] payload=%s resolved_client_id=%s resolved_style_id=%s",
                dict(request.data),
                client_id,
                style_id,
            )
            return detail_response(
                "client_id와 style_id를 모두 전달해 주세요.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        client = _get_client_or_404(client_id)
        return Response(
            {
                "status": "selected",
                "client_id": client.id,
                "style_id": int(style_id),
                "message": "선택한 스타일이 상담 요청 단계로 전달되었습니다.",
            }
        )


class ConfirmView(CompatEnvelopeAPIView):
    @extend_schema(
        summary="Confirm selected style and hand off to admin",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "string"},
                    "recommendation_id": {"type": "integer"},
                    "style_id": {"type": "integer"},
                    "selected_image_url": {"type": "string"},
                    "admin_id": {"type": "string"},
                    "source": {"type": "string", "example": "current_recommendations"},
                    "direct_consultation": {"type": "boolean", "default": False},
                },
                "required": ["client_id"],
            }
        },
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        logger.info(
            "[confirm_request] payload_keys=%s raw_client_id=%s raw_customer_id=%s raw_customer=%s raw_style_id=%s raw_recommendation_id=%s direct_consultation=%s",
            sorted(request.data.keys()),
            request.data.get("client_id"),
            request.data.get("customer_id"),
            request.data.get("customer"),
            request.data.get("style_id"),
            request.data.get("recommendation_id"),
            request.data.get("direct_consultation"),
        )
        client_id = _request_value(request, "client_id", "customer_id", "customer")
        if not client_id:
            logger.warning(
                "[confirm_missing_client_id] payload=%s",
                dict(request.data),
            )
            return detail_response("client_id is required.", status_code=status.HTTP_400_BAD_REQUEST)
        client = _get_client_or_404(client_id)
        try:
            payload = confirm_style_selection(
                client=client,
                recommendation_id=_request_value(request, "recommendation_id"),
                style_id=_request_value(request, "style_id"),
                selected_image_url=request.data.get("selected_image_url"),
                admin_id=request.data.get("admin_id"),
                source=request.data.get("source", "current_recommendations"),
                direct_consultation=bool(request.data.get("direct_consultation", False)),
            )
        except ValueError as exc:
            return detail_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


class CancelView(CompatEnvelopeAPIView):
    @extend_schema(
        summary="Cancel selected style and return to client input",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "string"},
                    "recommendation_id": {"type": "integer"},
                    "selected_image_url": {"type": "string"},
                    "source": {"type": "string", "example": "current_recommendations"},
                },
                "required": ["client_id"],
            }
        },
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        logger.info(
            "[cancel_request] payload_keys=%s raw_client_id=%s raw_customer_id=%s raw_customer=%s raw_recommendation_id=%s",
            sorted(request.data.keys()),
            request.data.get("client_id"),
            request.data.get("customer_id"),
            request.data.get("customer"),
            request.data.get("recommendation_id"),
        )
        client_id = _request_value(request, "client_id", "customer_id", "customer")
        if not client_id:
            logger.warning(
                "[cancel_missing_client_id] payload=%s",
                dict(request.data),
            )
            return detail_response("client_id is required.", status_code=status.HTTP_400_BAD_REQUEST)
        client = _get_client_or_404(client_id)
        try:
            payload = cancel_style_selection(
                client=client,
                recommendation_id=_request_value(request, "recommendation_id"),
                selected_image_url=request.data.get("selected_image_url"),
                source=request.data.get("source", "current_recommendations"),
            )
        except ValueError as exc:
            return detail_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


class ConsultView(ConfirmView):
    pass

