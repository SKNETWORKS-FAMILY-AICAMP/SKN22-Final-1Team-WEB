from __future__ import annotations

from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache

from app.front_views import admin_dashboard_page, admin_mypage_page, designer_dashboard_page
from app.session_state import (
    can_access_designer_dashboard,
    get_session_admin,
    get_session_designer,
)


@never_cache
def gated_partner_dashboard(request):
    """파트너 대시보드 게이트.

    매장 세션이 없으면 로그인 페이지로.
    PIN 인증 여부는 base_site.html의 JS 모달이 클라이언트 측에서 처리.
    """
    admin = get_session_admin(request=request)
    if admin is None:
        return redirect("partner_index")
    return admin_dashboard_page(request)


@never_cache
def gated_partner_mypage(request):
    """내 페이지 게이트.

    매장 세션이 없으면 로그인 페이지로.
    PIN 인증 여부는 base_site.html의 JS 모달이 클라이언트 측에서 처리.
    """
    admin = get_session_admin(request=request)
    if admin is None:
        return redirect("partner_index")
    return admin_mypage_page(request)


@never_cache
def gated_partner_staff_dashboard(request):
    designer = get_session_designer(request=request)
    if designer is None:
        if get_session_admin(request=request) is not None:
            return redirect("partner_designer_select")
        return redirect("partner_index")

    if not can_access_designer_dashboard(request=request):
        return redirect(
            f"{reverse('partner_designer_select')}?designer_id={designer.id}&next={reverse('partner_staff_dashboard')}"
        )

    # Keep the verified designer session alive until logout or expiry so
    # detail-to-dashboard navigation does not require PIN entry again.
    return designer_dashboard_page(request)
