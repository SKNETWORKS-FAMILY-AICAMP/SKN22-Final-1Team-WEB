import re

from django.contrib.auth.hashers import check_password
from django.http import HttpRequest, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from app.models_django import AdminAccount, Client
from app.session_state import (
    clear_admin_session,
    clear_customer_session,
    get_session_admin,
    get_session_customer,
    set_admin_session,
    set_customer_session,
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


def health_check(request):
    return JsonResponse({"status": "django_running", "framework": "Django"})


def home_page(request):
    return render(request, "index.html", {"start_url": "/customer/", "partner_url": "/partner/login/"})


def client_login_page(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        gender = (request.POST.get("gender") or "").strip()
        phone = _normalize_phone(request.POST.get("phone", ""))
        birth_year_estimate = _birth_year_from_age(request.POST.get("age"))
        if not name or not phone:
            return _render_customer_login(request, error_message="Name and phone are required.")

        client, _ = Client.objects.update_or_create(
            phone=phone,
            defaults={
                "name": name,
                "gender": gender,
                "age_input": (
                    int(request.POST.get("age"))
                    if (request.POST.get("age") or "").isdigit()
                    else None
                ),
                "birth_year_estimate": birth_year_estimate,
            },
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
    if not admin:
        return redirect("partner_index")
    return render(request, "admin/index.html", {"is_dashboard": True, "admin": admin})


def partner_verify(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST method is required."}, status=405)

    pin = (request.POST.get("pin") or "").strip()
    if not re.fullmatch(r"\d{4}", pin):
        return JsonResponse({"status": "error", "message": "PIN must be 4 digits."}, status=400)

    admin = None
    for candidate in AdminAccount.objects.filter(is_active=True).order_by("-created_at"):
        if check_password(pin, candidate.password_hash):
            admin = candidate
            break

    if admin is None:
        return JsonResponse({"status": "error", "message": "PIN did not match any active admin."}, status=401)

    set_admin_session(request=request, admin=admin)
    return JsonResponse({"status": "success", "redirect": "/partner/dashboard/"})


def logout_page(request):
    clear_customer_session(request=request)
    clear_admin_session(request=request)
    return redirect("index")


def page_not_found_view(request, exception):
    return render(request, "errors/error.html", {"error_code": "404"}, status=404)


def server_error_view(request):
    return render(request, "errors/error.html", {"error_code": "500"}, status=500)
