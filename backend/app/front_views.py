import re

from django.contrib.auth.hashers import check_password
from django.http import HttpRequest, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from app.api.v1.admin_services import register_admin
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


def _normalize_business_number(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _business_number_variants(value: str) -> set[str]:
    normalized = _normalize_business_number(value)
    if len(normalized) != 10:
        return {value}
    return {normalized, f"{normalized[:3]}-{normalized[3:5]}-{normalized[5:]}"}


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
    if not active_designers:
        defaults["assigned_at"] = timezone.now()
        defaults["assignment_source"] = "auto_shop_only"
    elif len(active_designers) == 1:
        defaults["designer"] = active_designers[0]
        defaults["assigned_at"] = timezone.now()
        defaults["assignment_source"] = "auto_single_designer"
    else:
        defaults["assignment_source"] = "shop_manual_assignment_pending"
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
        
        # New Flow: Step 1 Login -> Step 2 Camera
        return redirect("customer_camera")

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
    shop = get_session_admin(request=request)
    return render(request, "admin/index.html", {
        "is_dashboard": False,
        "active_shop": shop
    })


def admin_signup_page(request):
    if request.method == "POST":
        password = request.POST.get("password", "")
        password_confirm = request.POST.get("password_confirm", "")
        payload = {
            "name": (request.POST.get("name") or "").strip(),
            "store_name": (request.POST.get("store_name") or "").strip(),
            "role": (request.POST.get("role") or "owner").strip() or "owner",
            "phone": _normalize_phone(request.POST.get("phone", "")),
            "business_number": (
                request.POST.get("business_number")
                or request.POST.get("biz_number")
                or ""
            ).strip(),
            "password": password,
            "agree_terms": bool(request.POST.get("agree_terms")),
            "agree_privacy": bool(request.POST.get("agree_privacy")),
            "agree_third_party_sharing": bool(request.POST.get("agree_third_party_sharing")),
            "agree_marketing": bool(request.POST.get("agree_marketing")),
        }
        if password_confirm and password != password_confirm:
            return render(
                request,
                "admin/signup.html",
                {
                    "form_error": "비밀번호 확인이 일치하지 않습니다.",
                    "form_values": payload,
                },
                status=400,
            )
        try:
            result = register_admin(payload=payload)
        except ValueError as exc:
            return render(
                request,
                "admin/signup.html",
                {
                    "form_error": str(exc),
                    "form_values": payload,
                },
                status=400,
            )

        admin = AdminAccount.objects.filter(id=result["admin_id"], is_active=True).first()
        if admin is not None:
            clear_designer_session(request=request)
            set_admin_session(request=request, admin=admin)
        return redirect("partner_dashboard")

    return render(request, "admin/signup.html")


def admin_dashboard_page(request):
    admin = get_session_admin(request=request)
    designer = get_session_designer(request=request)
    if designer is not None:
        return redirect("partner_staff_dashboard")
    if not admin:
        return redirect("partner_index")
    return render(
        request,
        "admin/index.html",
        {
            "is_dashboard": True,
            "admin": admin,
            "designer": None,
            "is_designer_session": False,
            "is_shop_owner": True,
        },
    )


def designer_dashboard_page(request):
    designer = get_session_designer(request=request)
    if designer is None:
        return redirect("partner_index")
    return render(
        request,
        "admin/index.html",
        {
            "is_dashboard": True,
            "admin": designer.shop,
            "designer": designer,
            "is_designer_session": True,
            "is_shop_owner": False,
        },
    )


def partner_verify(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST method is required."}, status=405)

    designer_id = (request.POST.get("designer_id") or "").strip()
    business_number = _normalize_business_number(
        request.POST.get("biz_number", "") or request.POST.get("business_number", "")
    )
    password = (request.POST.get("password") or "").strip()
    pin = (request.POST.get("pin") or "").strip()

    if business_number and password:
        admin = AdminAccount.objects.filter(
            business_number__in=_business_number_variants(business_number),
            is_active=True,
        ).first()
        if not admin or not check_password(password, admin.password_hash):
            return JsonResponse(
                {"status": "error", "message": "사업자등록번호 또는 비밀번호를 다시 확인해 주세요."},
                status=401,
            )

        clear_designer_session(request=request)
        set_admin_session(request=request, admin=admin)
        return JsonResponse(
            {
                "status": "success",
                "redirect": "/partner/login/",
                "session_type": "admin",
                "next_step": "designer_select",
                "shop_id": admin.id,
                "store_name": admin.store_name,
            }
        )

    if designer_id:
        admin = get_session_admin(request=request)
        if admin is None:
            return JsonResponse(
                {"status": "error", "message": "먼저 매장 관리자 로그인이 필요합니다."},
                status=401,
            )
        if not re.fullmatch(r"\d{4}", pin):
            return JsonResponse({"status": "error", "message": "PIN 번호 4자리를 입력해 주세요."}, status=400)

        designer = (
            Designer.objects.select_related("shop")
            .filter(id=designer_id, shop=admin, is_active=True)
            .first()
        )
        if designer is None:
            return JsonResponse(
                {"status": "error", "message": "선택한 디자이너 정보를 찾을 수 없습니다."},
                status=404,
            )
        if not check_password(pin, designer.pin_hash):
            return JsonResponse({"status": "error", "message": "PIN 번호를 다시 확인해 주세요."}, status=401)

        set_admin_session(request=request, admin=designer.shop)
        set_designer_session(request=request, designer=designer)
        return JsonResponse(
            {
                "status": "success",
                "redirect": "/partner/staff/",
                "session_type": "designer",
                "shop_id": designer.shop_id,
                "designer_id": designer.id,
            }
        )

    if not re.fullmatch(r"\d{4}", pin):
        return JsonResponse({"status": "error", "message": "PIN 번호 4자리를 입력해 주세요."}, status=400)

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
                "redirect": "/partner/staff/",
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
        return JsonResponse({"status": "error", "message": "일치하는 관리자 또는 디자이너 PIN이 없습니다."}, status=401)

    clear_designer_session(request=request)
    set_admin_session(request=request, admin=admin)
    return JsonResponse({"status": "success", "redirect": "/partner/dashboard/", "session_type": "admin"})


def partner_designer_list(request):
    admin = get_session_admin(request=request)
    if admin is None:
        return JsonResponse({"status": "error", "message": "매장 관리자 로그인 후 이용해 주세요."}, status=401)
    if get_session_designer(request=request) is not None:
        return JsonResponse({"status": "error", "message": "디자이너 세션에서는 매장 관리자 기능에 접근할 수 없습니다."}, status=403)

    designers = [
        {
            "id": designer.id,
            "name": designer.name,
            "phone": designer.phone,
            "profile_image": None,
        }
        for designer in admin.designers.filter(is_active=True).order_by("id")
    ]
    return JsonResponse(designers, safe=False)


def logout_page(request):
    clear_customer_session(request=request)
    clear_admin_session(request=request)
    clear_designer_session(request=request)
    return redirect("index")


def page_not_found_view(request, exception):
    return render(request, "errors/error.html", {"error_code": "404"}, status=404)


def server_error_view(request):
    return render(request, "errors/error.html", {"error_code": "500"}, status=500)
