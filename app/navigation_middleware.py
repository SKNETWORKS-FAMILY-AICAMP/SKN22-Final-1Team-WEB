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
    revoke_owner_dashboard,
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
        current_main_route = self._resolve_current_main_route(request=request)
        if current_main_route is not None:
            return redirect(current_main_route)
        return None

    def _handle_customer_trend(self, request):
        current_main_route = self._resolve_current_main_route(request=request)
        if current_main_route is None:
            return redirect("index")
        client = get_session_customer(request=request)
        return render(
            request,
            "customer/trend.html",
            {
                "client": client,
                "trend_main_url": reverse(current_main_route),
            },
        )

    def _handle_customer_logout(self, request):
        clear_customer_session(request=request)
        if has_admin_session(request=request) or has_designer_session(request=request):
            return self._redirect_response(request, "partner_index")
        return self._redirect_response(request, "index")

    def _handle_designer_logout(self, request):
        clear_designer_session(request=request)
        revoke_owner_dashboard(request=request)
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
