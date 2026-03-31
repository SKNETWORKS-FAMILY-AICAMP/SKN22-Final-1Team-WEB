from django.shortcuts import render
from django.urls import path
from django.views.generic import RedirectView

from app.front_views import (
    admin_dashboard_page,
    admin_login_page,
    admin_signup_page,
    client_camera_page,
    client_login_page,
    client_recommendation_page,
    client_survey_page,
    designer_dashboard_page,
    health_check,
    home_page,
    logout_page,
    partner_verify,
    partner_designer_list,
    privacy_policy_page,
    terms_page,
)


urlpatterns = [
    path("", home_page, name="index"),
    path("health/", health_check, name="health-check"),
    path("docs/", lambda r: render(r, "pages/home.html"), name="docs"),
    path("terms/", terms_page, name="terms"),
    path("privacy-policy/", privacy_policy_page, name="privacy_policy"),
    path("customer/", client_login_page, name="customer_index"),
    path("customer/survey/", client_survey_page, name="customer_survey"),
    path("customer/survey/male/", client_survey_page, {"gender": "male"}, name="customer_survey_male"),
    path("customer/survey/female/", client_survey_page, {"gender": "female"}, name="customer_survey_female"),
    path("customer/camera/", client_camera_page, name="customer_camera"),
    path("customer/recommendations/", client_recommendation_page, name="customer_result"),
    path("customer/result/", client_recommendation_page, name="customer_result_legacy"),
    path("customer/logout/", logout_page, name="customer_logout"),
    path("demo/discovery/", lambda r: render(r, "demo/discovery.html"), name="demo_discovery"),
    path("partner/", admin_login_page, name="partner_index"),
    path("partner/login/", admin_login_page, name="partner_login"),
    path("partner/signup/", admin_signup_page, name="partner_signup"),
    path("partner/verify/", partner_verify, name="partner_verify"),
    path("partner/dashboard/", admin_dashboard_page, name="partner_dashboard"),
    path("partner/staff/", designer_dashboard_page, name="partner_staff_dashboard"),
    path("logout/", logout_page, name="logout"),
    path("api/v1/designers/", partner_designer_list, name="partner_designer_list"),
    # Legacy aliases kept for older links and docs.
    path("client/login/", client_login_page, name="client-login-shell"),
    path("client/survey/", client_survey_page, name="client-survey-shell"),
    path("client/recommendations/", client_recommendation_page, name="client-recommendation-shell"),
    path("admin-panel/login/", RedirectView.as_view(pattern_name="partner_index", permanent=False), name="admin-login-shell"),
    path("admin-panel/dashboard/", RedirectView.as_view(pattern_name="partner_index", permanent=False), name="admin-dashboard-shell"),
]
