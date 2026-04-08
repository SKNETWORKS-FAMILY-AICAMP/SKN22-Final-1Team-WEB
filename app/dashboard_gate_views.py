from __future__ import annotations

from django.shortcuts import redirect
from django.urls import reverse

from app.front_views import admin_dashboard_page, designer_dashboard_page
from app.session_state import (
    can_access_designer_dashboard,
    can_access_owner_dashboard,
    get_session_admin,
    get_session_designer,
    revoke_designer_dashboard,
)


def gated_partner_dashboard(request):
    designer = get_session_designer(request=request)
    if designer is not None:
        return redirect("partner_staff_dashboard")

    admin = get_session_admin(request=request)
    if admin is None:
        return redirect("partner_index")
    if not can_access_owner_dashboard(request=request):
        return redirect(f"{reverse('partner_designer_select')}?next={reverse('partner_dashboard')}")
    return admin_dashboard_page(request)


def gated_partner_staff_dashboard(request):
    designer = get_session_designer(request=request)
    if designer is None:
        if get_session_admin(request=request) is not None:
            return redirect("partner_designer_select")
        return redirect("partner_index")

    if not can_access_designer_dashboard(request=request):
        return redirect(f"{reverse('partner_designer_select')}?next={reverse('partner_staff_dashboard')}")

    # Consume the temporary access grant so the next fresh dashboard entry
    # requires PIN verification again.
    revoke_designer_dashboard(request=request)
    return designer_dashboard_page(request)
