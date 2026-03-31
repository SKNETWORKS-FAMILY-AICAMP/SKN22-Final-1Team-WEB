import re

from django.contrib.auth.hashers import check_password
from django.http import HttpRequest, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from app.models_django import AdminAccount, Client, Designer
from app.session_state import (
    clear_admin_session,
    clear_customer_session,
    clear_designer_session,
    get_session_admin,
    get_session_customer,
    get_session_designer,
    set_admin_session,
    set_customer_session,
    set_designer_session,
)


def _normalize_phone(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _birth_year_from_age(age_value: str) -> int | None:
    if not age_value:
        return None
    try:
        age = int(age_value)
    except (TypeError, ValueError):
        return None
    if age <= 0:
        return None
    return timezone.localdate().year - age


def _render_customer_login(request: HttpRequest, *, error_message: str | None = None):
    return render(request, "customer/index.html", {"form_error": error_message})


def _resolve_active_shop_and_designer(*, request: HttpRequest) -> tuple[AdminAccount | None, Designer | None]:
    designer = get_session_designer(request=request)
    admin = get_session_admin(request=request)
    if designer is not None:
        return designer.shop, designer
    return admin, None


def _resolve_client_assignment_defaults(*, request: HttpRequest) -> dict:
    shop, designer = _resolve_active_shop_and_designer(request=request)
    defaults: dict = {}
    if shop is not None:
        defaults["shop"] = shop

    if designer is not None:
        defaults["designer"] = designer
        defaults["assigned_at"] = timezone.now()
        defaults["assignment_source"] = "designer_session"
        return defaults

    if shop is None:
        return defaults

    active_designers = list(shop.designers.filter(is_active=True).order_by("id")[:2])
    if len(active_designers) == 1:
        defaults["designer"] = active_designers[0]
        defaults["assigned_at"] = timezone.now()
        defaults["assignment_source"] = "auto_single_designer"
    elif active_designers:
        defaults["assignment_source"] = "shop_session_unassigned"
    return defaults


def health_check(request):
    return JsonResponse({"status": "django_running", "framework": "Django"})


def home_page(request):
    return render(request, "index.html", {"start_url": "/customer/", "partner_url": "/partner/login/"})


def terms_page(request):
    return render(request, "pages/terms.html")


def privacy_policy_page(request):
    return render(request, "pages/privacy_policy.html")


def client_login_page(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        gender = (request.POST.get("gender") or "").strip()
        phone = _normalize_phone(request.POST.get("phone", ""))
        birth_year_estimate = _birth_year_from_age(request.POST.get("age"))
        if not name or not phone:
            return _render_customer_login(request, error_message="Name and phone are required.")

        defaults = {
            "name": name,
            "gender": gender,
            "age_input": (
                int(request.POST.get("age"))
                if (request.POST.get("age") or "").isdigit()
                else None
            ),
            "birth_year_estimate": birth_year_estimate,
        }
        defaults.update(_resolve_client_assignment_defaults(request=request))

        client, _ = Client.objects.update_or_create(
            phone=phone,
            defaults=defaults,
        )
        set_customer_session(request=request, client=client)
        
        # 성별에 따른 전용 URL로 리다이렉트
        if gender == "male":
            return redirect("customer_survey_male")
        elif gender == "female":
            return redirect("customer_survey_female")
        return redirect("customer_survey")

    return _render_customer_login(request)


def client_survey_page(request, gender=None):
    client = get_session_customer(request=request)
    if not client:
        return redirect("customer_index")
    
    # URL 파라미터로 받은 gender가 있다면 우선순위 적용 (수동 접근 대응)
    display_gender = gender if gender else client.gender
    
    return render(request, "customer/survey.html", {
        "client": client,
        "display_gender": display_gender
    })


def client_camera_page(request):
    if not get_session_customer(request=request):
        return redirect("customer_index")
    return render(request, "customer/camera.html")


def client_recommendation_page(request):
    if not get_session_customer(request=request):
        return redirect("customer_index")
    return render(request, "customer/result.html")


def admin_login_page(request):
    return render(request, "admin/index.html", {"is_dashboard": False})


def admin_signup_page(request):
    return render(request, "admin/signup.html")


def admin_dashboard_page(request):
    admin = get_session_admin(request=request)
    designer = get_session_designer(request=request)
    if not admin and designer is not None:
        admin = designer.shop
    if not admin:
        return redirect("partner_index")
    return render(
        request,
        "admin/index.html",
        {
            "is_dashboard": True,
            "admin": admin,
            "designer": designer,
            "is_designer_session": bool(designer),
        },
    )


def partner_verify(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST method is required."}, status=405)

    pin = (request.POST.get("pin") or "").strip()
    if not re.fullmatch(r"\d{4}", pin):
        return JsonResponse({"status": "error", "message": "PIN must be 4 digits."}, status=400)

    designer = None
    for candidate in Designer.objects.select_related("shop").filter(is_active=True).order_by("-created_at"):
        if check_password(pin, candidate.pin_hash):
            designer = candidate
            break

    if designer is not None:
        set_admin_session(request=request, admin=designer.shop)
        set_designer_session(request=request, designer=designer)
        return JsonResponse(
            {
                "status": "success",
                "redirect": "/partner/dashboard/",
                "session_type": "designer",
                "shop_id": designer.shop_id,
                "designer_id": designer.id,
            }
        )

    admin = None
    for candidate in AdminAccount.objects.filter(is_active=True).order_by("-created_at"):
        if check_password(pin, candidate.password_hash):
            admin = candidate
            break

    if admin is None:
        return JsonResponse({"status": "error", "message": "PIN did not match any active admin."}, status=401)

    clear_designer_session(request=request)
    set_admin_session(request=request, admin=admin)
    return JsonResponse({"status": "success", "redirect": "/partner/dashboard/", "session_type": "admin"})


def logout_page(request):
    clear_customer_session(request=request)
    clear_admin_session(request=request)
    clear_designer_session(request=request)
    return redirect("index")


def page_not_found_view(request, exception):
    return render(request, "errors/error.html", {"error_code": "404"}, status=404)


def server_error_view(request):
    return render(request, "errors/error.html", {"error_code": "500"}, status=500)
