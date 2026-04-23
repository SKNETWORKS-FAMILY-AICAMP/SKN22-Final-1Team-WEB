from __future__ import annotations

from typing import TYPE_CHECKING

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from app.session_state import (
    clear_customer_session,
    clear_designer_session,
    get_session_admin,
    get_session_customer,
    get_session_designer,
    has_admin_session,
    has_designer_session,
    revoke_all_owner_scopes,
)

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


class CurrentFlowNavigationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        view_name = getattr(getattr(request, "resolver_match", None), "url_name", None)

        # 관리자 인증 세션 자동 해제 로직: 보호된 영역을 벗어날 때만 실행
        self._handle_admin_session_revocation(request, view_name)

        if view_name == "index":
            return self._handle_home(request)
        if view_name == "customer_trend":
            return self._handle_customer_trend(request)
        if view_name == "customer_logout":
            return self._handle_customer_logout(request)
        if view_name == "designer_logout":
            return self._handle_designer_logout(request)
        if view_name == "partner_dashboard":
            return self._handle_partner_dashboard(request)
        if view_name == "partner_dashboard_enter":
            return self._handle_partner_dashboard_enter(request)
        return None

    def _handle_admin_session_revocation(self, request, view_name):
        if not view_name:
            return

        # 명시적으로 관리자 영역을 '벗어나는' 뷰 리스트
        # 이 페이지들로 이동할 때만 admin-pin 인증을 해제합니다.
        exit_views = {
            "index",                            # 메인 랜딩
            "partner_index",                    # 매장 로그인 페이지
            "partner_designer_select",          # 디자이너 선택 화면
            "customer_index",                   # 고객 분석 시작
            "customer_camera",                  # 카메라
            "customer_menu",                    # 고객 메뉴
            "customer_survey",                  # 설문
            "customer_recommendation",          # 결과
            "customer_history",                 # 히스토리
            "customer_trend",                   # 트렌드
            "customer_consultation_complete",   # 상담 완료
            "customer_logout",                  # 고객 로그아웃
            "designer_logout",                  # 디자이너 로그아웃
            "logout",                           # 전체 로그아웃
        }

        # 나가는 페이지로 이동할 때만 인증 해제
        if view_name in exit_views:
            if request.session.get("owner_dashboard_allowed") or request.session.get("owner_mypage_allowed"):
                revoke_all_owner_scopes(request=request)
                request.session.modified = True

    def _resolve_current_main_route(self, *, request: HttpRequest, include_customer: bool = True) -> str | None:
        if include_customer and get_session_customer(request=request) is not None:
            return "customer_menu"
        if get_session_designer(request=request) is not None:
            return "partner_staff_dashboard"
        if get_session_admin(request=request) is not None:
            return "partner_dashboard"
        return None

    def _redirect_response(self, request: HttpRequest, route_name: str, *, ajax_route_name: str | None = None):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            target_route = ajax_route_name or route_name
            return JsonResponse({"status": "success", "redirect": reverse(target_route)})
        return redirect(route_name)

    def _handle_home(self, request):
        # 고객이나 디자이너 세션이 있는 경우에만 각자의 메인 대시보드로 강제 이동
        if get_session_customer(request=request) is not None:
            return redirect("customer_menu")
        if get_session_designer(request=request) is not None:
            return redirect("partner_staff_dashboard")
        
        # 매장 관리자(Owner)는 메인 페이지(landing)를 볼 수 있도록 허용 (인증 해제를 유도하기 위함)
        return None

    def _handle_customer_trend(self, request):
        current_main_route = self._resolve_current_main_route(request=request)
        back_url = reverse(current_main_route) if current_main_route else reverse("index")
        client = get_session_customer(request=request)
        return render(
            request,
            "customer/trend.html",
            {
                "client": client,
                "back_url": back_url,
                "trend_main_url": back_url,
            },
        )

    def _handle_customer_logout(self, request):
        client = get_session_customer(request=request)
        if client is not None:
            try:
                from app.api.v1.admin_services import close_consultation_session
                from app.services.model_team_bridge import get_legacy_active_consultation_items

                active_items = get_legacy_active_consultation_items(client=client) or []
                active_item = active_items[0] if active_items else None
                consultation_id = active_item.get("consultation_id") if isinstance(active_item, dict) else None
                if consultation_id not in (None, ""):
                    close_consultation_session(
                        consultation_id=int(consultation_id),
                        client=client,
                        admin=getattr(client, "shop", None),
                        designer=getattr(client, "designer", None),
                    )
            except Exception:
                pass
        clear_customer_session(request=request)
        if has_admin_session(request=request) or has_designer_session(request=request):
            return self._redirect_response(request, "partner_index")
        return self._redirect_response(request, "index")

    def _handle_designer_logout(self, request):
        clear_designer_session(request=request)
        revoke_all_owner_scopes(request=request)
        if has_admin_session(request=request):
            return self._redirect_response(request, "partner_index", ajax_route_name="partner_designer_select")
        return self._redirect_response(request, "partner_index")

    def _handle_partner_dashboard(self, request):
        designer = get_session_designer(request=request)
        if designer is not None:
            return redirect("partner_staff_dashboard")

        admin = get_session_admin(request=request)
        if admin is None:
            return redirect("partner_designer_select")

        return None

    def _handle_partner_dashboard_enter(self, request):
        designer = get_session_designer(request=request)
        if designer is not None:
            return redirect("partner_staff_dashboard")

        admin = get_session_admin(request=request)
        if admin is None:
            return redirect("partner_designer_select")

        return None
