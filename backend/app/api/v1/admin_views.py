from django.shortcuts import get_object_or_404
import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema

from app.api.v1.admin_auth import AdminTokenAuthentication, IsAuthenticatedAdmin, refresh_admin_access_token
from app.api.v1.response_helpers import CompatEnvelopeAPIView, detail_response
from app.api.v1.admin_serializers import (
    AdminLoginSerializer,
    AdminRegisterSerializer,
    AdminTrendFilterSerializer,
    ConsultationCloseSerializer,
    ConsultationNoteCreateSerializer,
    ChatbotAskSerializer,
    RefreshTokenSerializer,
)
from app.api.v1.admin_services import (
    _scoped_client_queryset,
    assign_client_to_designer,
    close_consultation_session,
    create_client_note,
    get_active_client_sessions,
    get_admin_profile,
    get_admin_dashboard_summary,
    get_admin_trend_report,
    get_all_clients,
    get_client_detail,
    get_client_recommendation_report,
    get_style_report,
    login_admin,
    register_admin,
)
from app.models_django import AdminAccount, CaptureRecord, Client, ConsultationRequest, Designer
from app.session_state import get_session_admin, get_session_designer, set_admin_session
from app.services.ai_facade import get_ai_health
from app.services.chatbot_service import build_admin_chatbot_reply, get_chatbot_backend_status


logger = logging.getLogger(__name__)


def _build_admin_register_errors(message: str) -> dict[str, list[str]]:
    lowered = message.lower()
    if "phone number" in lowered or "연락처" in message:
        return {"phone": [message]}
    if "business registration number" in lowered or "사업자등록번호" in message:
        return {"business_number": [message]}
    return {"non_field_errors": [message]}


def _build_admin_login_errors(message: str) -> dict[str, list[str]]:
    return {"non_field_errors": [message]}


def _resolve_request_admin(request) -> AdminAccount | None:
    if isinstance(getattr(request, "user", None), AdminAccount):
        return request.user
    return get_session_admin(request=request)


def _resolve_request_designer(request) -> Designer | None:
    return get_session_designer(request=request)


def _resolve_request_staff(request) -> tuple[AdminAccount | None, Designer | None]:
    admin = _resolve_request_admin(request)
    designer = _resolve_request_designer(request)
    if admin is None and designer is not None:
        admin = designer.shop
    return admin, designer


def _legacy_staff_required(request):
    admin, designer = _resolve_request_staff(request)
    if admin is None:
        return None, detail_response("Admin login is required.", status_code=status.HTTP_401_UNAUTHORIZED)
    return (admin, designer), None


def _legacy_shop_required(request):
    staff, error_response = _legacy_staff_required(request)
    if error_response:
        return None, error_response
    admin, designer = staff
    if designer is not None:
        return None, detail_response(
            "디자이너 세션에서는 고객 배정을 변경할 수 없습니다.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return admin, None


class AdminProtectedAPIView(CompatEnvelopeAPIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticatedAdmin]


class AdminRegisterView(CompatEnvelopeAPIView):
    @extend_schema(summary="Register admin", request=AdminRegisterSerializer, responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT})
    def post(self, request):
        serializer = AdminRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = register_admin(payload=serializer.validated_data)
        except ValueError as exc:
            message = str(exc)
            return detail_response(
                message,
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="validation_error",
                errors=_build_admin_register_errors(message),
            )
        admin = AdminAccount.objects.filter(id=payload["admin_id"], is_active=True).first()
        if admin is not None:
            set_admin_session(request=request, admin=admin)
            payload["redirect"] = "/partner/dashboard/"
            payload["session_type"] = "admin"
        return Response(payload, status=status.HTTP_201_CREATED)


class AdminLoginView(CompatEnvelopeAPIView):
    @extend_schema(summary="Login admin", request=AdminLoginSerializer, responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT})
    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = login_admin(**serializer.validated_data)
        except ValueError as exc:
            message = str(exc)
            return detail_response(
                message,
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="validation_error",
                errors=_build_admin_login_errors(message),
            )
        admin = AdminAccount.objects.filter(id=payload["admin"]["admin_id"], is_active=True).first()
        if admin is not None:
            set_admin_session(request=request, admin=admin)
            payload["redirect"] = "/partner/dashboard/"
            payload["session_type"] = "admin"
        return Response(payload)


class AdminRefreshView(CompatEnvelopeAPIView):
    @extend_schema(summary="Refresh admin token", request=RefreshTokenSerializer, responses={200: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT})
    def post(self, request):
        serializer = RefreshTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = refresh_admin_access_token(refresh_token=serializer.validated_data["refresh_token"])
        except Exception as exc:
            logger.warning("[admin_refresh_failed] reason=%s", exc)
            return detail_response(str(exc), status_code=status.HTTP_401_UNAUTHORIZED)
        return Response(payload)


class AdminProfileView(AdminProtectedAPIView):
    @extend_schema(summary="Get current admin profile", responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(get_admin_profile(admin=request.user))


class AdminDashboardView(AdminProtectedAPIView):
    @extend_schema(summary="Admin dashboard summary", responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(get_admin_dashboard_summary(admin=request.user))


class ActiveClientSessionsView(AdminProtectedAPIView):
    @extend_schema(summary="Active client sessions", responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(get_active_client_sessions(admin=request.user))


class AllClientsView(AdminProtectedAPIView):
    @extend_schema(
        summary="All clients for admin",
        parameters=[OpenApiParameter("q", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False)],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        return Response(get_all_clients(query=request.query_params.get("q", ""), admin=request.user))


class LegacyAllClientsView(CompatEnvelopeAPIView):
    @extend_schema(
        summary="Legacy customer list for template dashboard",
        parameters=[OpenApiParameter("q", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False)],
        responses={200: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        staff, error_response = _legacy_staff_required(request)
        if error_response:
            return error_response
        admin, designer = staff

        payload = get_all_clients(query=request.query_params.get("q", ""), admin=admin, designer=designer)
        items = [
            {
                "id": item["client_id"],
                "name": item["name"],
                "phone": item["phone"],
                "created_at": item["created_at"],
                "designer_id": item["designer_id"],
                "designer_name": item["designer_name"],
                "assigned_at": item["assigned_at"],
                "assignment_source": item["assignment_source"],
                "is_assignment_pending": item["is_assignment_pending"],
            }
            for item in payload["items"]
        ]
        return Response(items)


class AdminClientDetailView(AdminProtectedAPIView):
    @extend_schema(
        summary="Admin client detail",
        parameters=[OpenApiParameter("client_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True)],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        client = get_object_or_404(Client, id=request.query_params.get("client_id"))
        try:
            return Response(get_client_detail(client=client, admin=request.user))
        except ValueError as exc:
            return detail_response(str(exc), status_code=status.HTTP_404_NOT_FOUND)


class LegacyAdminClientDetailView(CompatEnvelopeAPIView):
    @extend_schema(
        summary="Legacy customer detail for template dashboard",
        responses={200: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def get(self, request, pk: int):
        staff, error_response = _legacy_staff_required(request)
        if error_response:
            return error_response
        admin, designer = staff

        client = get_object_or_404(Client, id=pk)
        try:
            payload = get_client_detail(client=client, admin=admin, designer=designer)
        except ValueError as exc:
            return detail_response(str(exc), status_code=status.HTTP_404_NOT_FOUND)

        return Response(
            {
                "id": payload["client"]["client_id"],
                "name": payload["client"]["name"],
                "phone": payload["client"]["phone"],
                "survey": payload.get("latest_survey"),
                "face_analyses": payload["analysis_history"],
                "captures": [
                    {
                        "processed_path": (
                            row.get("processed_image_url")
                            or row.get("deidentified_image_url")
                            or row.get("original_image_url")
                        ),
                        "created_at": row.get("created_at"),
                    }
                    for row in payload["capture_history"]
                ],
            }
        )


class LegacyAdminClientAssignView(CompatEnvelopeAPIView):
    @extend_schema(
        summary="Assign a customer to a designer for the active shop session",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def post(self, request, pk: int):
        admin, error_response = _legacy_shop_required(request)
        if error_response:
            return error_response

        designer_id = request.data.get("designer_id")
        if designer_id in (None, ""):
            return detail_response("디자이너를 선택해 주세요.", status_code=status.HTTP_400_BAD_REQUEST)

        try:
            designer_id = int(designer_id)
        except (TypeError, ValueError):
            return detail_response("디자이너 정보가 올바르지 않습니다.", status_code=status.HTTP_400_BAD_REQUEST)

        client = get_object_or_404(Client, id=pk)
        scoped_ids = set(_scoped_client_queryset(admin=admin).values_list("id", flat=True))
        if client.id not in scoped_ids:
            return detail_response("현재 매장 범위를 벗어난 고객입니다.", status_code=status.HTTP_404_NOT_FOUND)

        try:
            payload = assign_client_to_designer(client=client, designer_id=designer_id, admin=admin)
        except ValueError as exc:
            return detail_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


class AdminClientRecommendationView(AdminProtectedAPIView):
    @extend_schema(
        summary="Admin client recommendation report",
        parameters=[OpenApiParameter("client_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True)],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        client = get_object_or_404(Client, id=request.query_params.get("client_id"))
        try:
            return Response(get_client_recommendation_report(client=client, admin=request.user))
        except ValueError as exc:
            return detail_response(str(exc), status_code=status.HTTP_404_NOT_FOUND)


class ConsultationNoteView(AdminProtectedAPIView):
    @extend_schema(summary="Create client consultation note", request=ConsultationNoteCreateSerializer, responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT})
    def post(self, request):
        serializer = ConsultationNoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client = get_object_or_404(Client, id=serializer.validated_data["client_id"])
        try:
            payload = create_client_note(
                client=client,
                consultation_id=serializer.validated_data["consultation_id"],
                content=serializer.validated_data["content"],
                admin=request.user,
            )
        except ValueError as exc:
            return detail_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


class ConsultationCloseView(AdminProtectedAPIView):
    @extend_schema(summary="Close consultation session", request=ConsultationCloseSerializer, responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT})
    def post(self, request):
        serializer = ConsultationCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = close_consultation_session(consultation_id=serializer.validated_data["consultation_id"], admin=request.user)
        except ValueError as exc:
            return detail_response(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


class AdminTrendReportView(AdminProtectedAPIView):
    @extend_schema(
        summary="Admin weekly trend report",
        parameters=[
            OpenApiParameter("days", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("target_length", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("target_vibe", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("scalp_type", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("hair_colour", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("budget_range", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("age_decade", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("age_segment", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("age_group", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        serializer = AdminTrendFilterSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        days = data.pop("days", 7)
        logger.info(
            "[admin_trend_report_request] admin_id=%s days=%s filters=%s",
            request.user.id,
            days,
            data,
        )
        return Response(get_admin_trend_report(days=days, filters=data, admin=request.user))


class LegacyAdminTrendReportView(CompatEnvelopeAPIView):
    @extend_schema(summary="Legacy trend report for template dashboard", responses={200: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT})
    def get(self, request):
        admin, error_response = _legacy_shop_required(request)
        if error_response:
            return error_response

        days = int(request.query_params.get("days", 7))
        # Trend reporting is store-wide even when a designer session is active.
        trend_payload = get_admin_trend_report(days=days, filters={}, admin=admin, designer=None)
        clients_payload = get_all_clients(admin=admin, designer=None)
        client_ids = [item["client_id"] for item in clients_payload["items"]]
        client_filter = {"client_id__in": client_ids} if client_ids else {}
        start_date = timezone.localdate() - timezone.timedelta(days=days - 1)
        activity_by_day: dict[str, set[int]] = {
            (start_date + timezone.timedelta(days=offset)).isoformat(): set()
            for offset in range(days)
        }

        for created_at, client_id in CaptureRecord.objects.filter(
            created_at__date__gte=start_date,
            **client_filter,
        ).values_list("created_at", "client_id"):
            activity_by_day[timezone.localtime(created_at).date().isoformat()].add(client_id)

        for created_at, client_id in ConsultationRequest.objects.filter(
            created_at__date__gte=start_date,
            **client_filter,
        ).values_list("created_at", "client_id"):
            activity_by_day[timezone.localtime(created_at).date().isoformat()].add(client_id)

        total_customers = len(clients_payload["items"])
        new_today = sum(
            1
            for item in clients_payload["items"]
            if timezone.localtime(item["created_at"]).date() == timezone.localdate()
        )
        unique_clients = trend_payload["kpi"]["unique_clients"]
        conversion_rate = round(
            (trend_payload["kpi"]["total_confirmations"] / unique_clients) * 100
        ) if unique_clients else 0

        return Response(
            {
                "summary": {
                    "total_customers": total_customers,
                    "new_today": new_today,
                    "conversion_rate": conversion_rate,
                },
                "visitor_stats": [
                    {"date": date, "count": len(client_set)}
                    for date, client_set in activity_by_day.items()
                ],
                "style_distribution": [
                    {"name": item["style_name"], "value": item["selection_count"]}
                    for item in trend_payload["distribution"]
                ],
            }
        )


class StyleReportView(AdminProtectedAPIView):
    @extend_schema(
        summary="Style report for admin",
        parameters=[
            OpenApiParameter("style_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True),
            OpenApiParameter("days", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        style_id = int(request.query_params.get("style_id"))
        days = int(request.query_params.get("days", 7))
        logger.info(
            "[admin_style_report_request] admin_id=%s style_id=%s days=%s",
            request.user.id,
            style_id,
            days,
        )
        return Response(get_style_report(style_id=style_id, days=days, admin=request.user))


class AdminChatbotAskView(CompatEnvelopeAPIView):
    authentication_classes = [AdminTokenAuthentication]

    @extend_schema(
        summary="Ask admin chatbot for styling guidance",
        request=ChatbotAskSerializer,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        admin, designer = _resolve_request_staff(request)
        if admin is None:
            return detail_response("Admin login is required.", status_code=status.HTTP_401_UNAUTHORIZED)

        serializer = ChatbotAskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = build_admin_chatbot_reply(
            message=serializer.validated_data["message"],
            admin_name=(designer.name if designer is not None else admin.name),
            store_name=admin.store_name,
        )
        logger.info(
            "[admin_chatbot_reply] admin_id=%s designer_id=%s store_name=%s message=%s",
            admin.id,
            (designer.id if designer is not None else None),
            admin.store_name,
            serializer.validated_data["message"][:120],
        )
        payload["actor_type"] = "designer" if designer is not None else "admin"
        payload["designer_id"] = designer.id if designer is not None else None
        return Response(payload)


class AdminAiHealthView(CompatEnvelopeAPIView):
    authentication_classes = [AdminTokenAuthentication]

    @extend_schema(
        summary="Get AI backend health and chatbot routing status",
        responses={200: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        admin, designer = _resolve_request_staff(request)
        if admin is None:
            return detail_response("Admin login is required.", status_code=status.HTTP_401_UNAUTHORIZED)

        return Response(
            {
                "status": "ready",
                "checked_at": timezone.now(),
                "actor_type": "designer" if designer is not None else "admin",
                "designer_id": designer.id if designer is not None else None,
                "ai_engine": get_ai_health(),
                "chatbot_backend": get_chatbot_backend_status(),
            }
        )

