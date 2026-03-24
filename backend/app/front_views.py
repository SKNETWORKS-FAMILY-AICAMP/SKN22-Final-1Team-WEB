from django.http import JsonResponse
from django.shortcuts import render


def health_check(request):
    return JsonResponse({"status": "django_running", "framework": "Django"})


def _render_shell(request, *, template_name: str, title: str, subtitle: str, api_map: list[dict]):
    return render(
        request,
        template_name,
        {
            "page_title": title,
            "page_subtitle": subtitle,
            "api_map": api_map,
        },
    )


def home_page(request):
    return render(request, "index.html", {"start_url": "/customer/", "partner_url": "/partner/login/"})


def client_login_page(request):
    return render(request, "customer/index.html")


def client_survey_page(request):
    return render(request, "customer/survey.html")


def client_camera_page(request):
    return render(request, "customer/camera.html")


def client_recommendation_page(request):
    return render(request, "customer/result.html")


def admin_login_page(request):
    return render(request, "admin/login.html")


def admin_dashboard_page(request):
    return render(request, "admin/index.html")

