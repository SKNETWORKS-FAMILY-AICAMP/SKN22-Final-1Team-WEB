import io
import shutil
import tempfile
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APITestCase

from app.api.v1.admin_auth import (
    ADMIN_ACCESS_TOKEN_SALT,
    ADMIN_REFRESH_TOKEN_SALT,
    CLIENT_REFRESH_TOKEN_SALT,
)
from app.api.v1.admin_services import register_admin
from app.api.v1.services_django import confirm_style_selection, get_latest_survey, persist_generated_batch, upsert_survey
from app.models_django import AdminAccount, CaptureRecord, Client, Designer, FaceAnalysis, Style, StyleSelection, Survey
from app.models_model_team import LegacyHairstyle
from app.services.model_team_bridge import (
    complete_legacy_capture_analysis,
    create_designer_record,
    create_legacy_capture_upload_record,
    get_admin_by_identifier,
    get_admin_by_phone,
    get_client_by_identifier,
    get_client_by_phone,
    get_designers_for_admin,
    get_designer_by_identifier,
    get_legacy_admin_id,
    get_legacy_client_id,
    get_legacy_designer_id,
    upsert_client_record,
)
from app.tests.test_legacy_model_sync import LEGACY_TABLE_DDL, LEGACY_TABLES
from django.db import connection


def build_valid_business_number(prefix: str = "123456789") -> str:
    digits = [int(char) for char in prefix]
    weights = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    checksum = sum(digit * weight for digit, weight in zip(digits, weights))
    checksum += (digits[8] * 5) // 10
    check_digit = (10 - (checksum % 10)) % 10
    return prefix + str(check_digit)


@override_settings(
    SUPABASE_USE_REMOTE_STORAGE=False,
    STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
)
class FrontCompatibilityTests(APITestCase):
    def setUp(self):
        self.temp_media_root = tempfile.mkdtemp(prefix="mirrai-front-compat-")
        self.media_override = override_settings(MEDIA_ROOT=self.temp_media_root)
        self.media_override.enable()
        with connection.cursor() as cursor:
            for ddl in LEGACY_TABLE_DDL:
                cursor.execute(ddl)

    def tearDown(self):
        self.media_override.disable()
        with connection.cursor() as cursor:
            for table in LEGACY_TABLES:
                cursor.execute(f"DROP TABLE IF EXISTS {table}")
        shutil.rmtree(self.temp_media_root, ignore_errors=True)

    def _set_admin_session(self, admin):
        session = self.client.session
        session["admin_id"] = admin.id
        session["admin_legacy_id"] = get_legacy_admin_id(admin=admin)
        session["admin_name"] = admin.name
        session.save()

    def _set_designer_session(self, designer):
        session = self.client.session
        session["designer_id"] = designer.id
        session["designer_legacy_id"] = get_legacy_designer_id(designer=designer)
        session["designer_name"] = designer.name
        session["admin_id"] = designer.shop_id
        session["admin_legacy_id"] = get_legacy_admin_id(admin=designer.shop)
        session["admin_name"] = designer.shop.name
        session.save()

    def _assert_never_cache_headers(self, response):
        self.assertIn("Cache-Control", response)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("no-cache", response["Cache-Control"])

    def _attach_refresh(self, obj, resolver):
        identifier = getattr(obj, "id", None)

        def _refresh():
            latest = resolver(identifier=identifier)
            self.assertIsNotNone(latest)
            obj.__dict__.update(latest.__dict__)

        obj.refresh_from_db = _refresh
        return obj

    def _create_admin(self, **kwargs):
        raw_password = kwargs.get("raw_password")
        if not raw_password and kwargs.get("password_hash"):
            for candidate in ("pw1234!!", "1234", "9999", "1000"):
                if check_password(candidate, kwargs["password_hash"]):
                    raw_password = candidate
                    break
        admin = register_admin(
            payload={
                "name": kwargs["name"],
                "store_name": kwargs["store_name"],
                "role": kwargs.get("role", "owner"),
                "phone": kwargs["phone"],
                "business_number": kwargs["business_number"],
                "password": raw_password or "pw1234!!",
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
                "agree_marketing": bool(kwargs.get("agree_marketing", False)),
            }
        )
        admin_obj = get_admin_by_identifier(identifier=admin["admin_id"])
        self.assertIsNotNone(admin_obj)
        if kwargs.get("password_hash"):
            self.assertTrue(admin_obj.password_hash)
        return self._attach_refresh(admin_obj, get_admin_by_identifier)

    def _create_designer(self, **kwargs):
        raw_pin = kwargs.get("raw_pin")
        if not raw_pin and kwargs.get("pin_hash"):
            for candidate in ("1234", "2468", "5678", "9999", "1111", "2222", "1357"):
                if check_password(candidate, kwargs["pin_hash"]):
                    raw_pin = candidate
                    break
        designer = create_designer_record(
            admin=kwargs["shop"],
            name=kwargs["name"],
            phone=kwargs.get("phone", ""),
            pin_hash=kwargs.get("pin_hash") or make_password(raw_pin or "1234"),
        )
        return self._attach_refresh(designer, get_designer_by_identifier)

    def _create_client(self, **kwargs):
        client = upsert_client_record(
            phone=kwargs["phone"],
            name=kwargs["name"],
            gender=kwargs.get("gender"),
            age_input=kwargs.get("age_input"),
            birth_year_estimate=kwargs.get("birth_year_estimate"),
            shop=kwargs.get("shop"),
            designer=kwargs.get("designer"),
            assignment_source=kwargs.get("assignment_source"),
        )
        return self._attach_refresh(client, get_client_by_identifier)

    def _create_legacy_hairstyle(self, *, style_id: int, style_name: str, vibe: str = "natural"):
        LegacyHairstyle.objects.update_or_create(
            hairstyle_id=style_id,
            defaults={
                "chroma_id": str(style_id),
                "style_name": style_name,
                "image_url": f"https://example.com/styles/{style_id}.jpg",
                "created_at": timezone.now().isoformat(),
                "backend_style_id": style_id,
                "name": style_name,
                "vibe": vibe,
                "description": f"{style_name} description",
            },
        )
        return SimpleNamespace(id=style_id, style_name=style_name, name=style_name, vibe=vibe)

    def _get_admin_by_phone(self, phone: str):
        admin = get_admin_by_phone(phone=phone)
        self.assertIsNotNone(admin)
        return admin

    def _get_client_by_phone(self, phone: str):
        client = get_client_by_phone(phone=phone)
        self.assertIsNotNone(client)
        return client

    def _seed_generated_batch(self, *, client, face_shape: str = "Oval", target_length: str = "short", target_vibe: str = "soft"):
        survey = upsert_survey(
            client,
            {
                "target_length": target_length,
                "target_vibe": target_vibe,
                "scalp_type": "normal",
                "hair_colour": "black",
                "budget_range": "10-15",
            },
        )
        capture = create_legacy_capture_upload_record(
            client=client,
            original_path="captures/original.jpg",
            processed_path="captures/processed.jpg",
            filename="capture.jpg",
            status="DONE",
            face_count=1,
            landmark_snapshot={"version": "coarse-v1"},
            deidentified_path="captures/deidentified.jpg",
            privacy_snapshot={"storage_policy": "asset_store"},
            error_note=None,
        )
        _, analysis = complete_legacy_capture_analysis(
            record_id=capture.id,
            face_shape=face_shape,
            golden_ratio_score=0.91,
            landmark_snapshot={"version": "coarse-v1"},
        )
        self.assertIsNotNone(analysis)
        return persist_generated_batch(client=client, capture_record=capture, survey=survey, analysis=analysis)

    def test_customer_form_post_creates_session_and_redirects(self):
        response = self.client.post(
            "/customer/",
            {
                "name": "Kim User",
                "gender": "female",
                "age": "27",
                "phone": "010-1234-5678",
                "agree_privacy": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/customer/menu/"))
        session = self.client.session
        self.assertIsNotNone(session.get("customer_id"))
        self.assertEqual(session.get("customer_name"), "Kim User")

    def test_customer_menu_sets_never_cache_headers(self):
        client = self._create_client(name="Cache Client", phone="01011112222")
        session = self.client.session
        session["customer_id"] = client.id
        session["customer_name"] = client.name
        session.save()

        response = self.client.get("/customer/menu/")

        self.assertEqual(response.status_code, 200)
        self._assert_never_cache_headers(response)

    def test_partner_login_sets_never_cache_headers(self):
        response = self.client.get("/partner/")

        self.assertEqual(response.status_code, 200)
        self._assert_never_cache_headers(response)

    def test_partner_login_includes_bfcache_reload_script(self):
        response = self.client.get("/partner/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "window.addEventListener('pageshow'", html=False)

    def test_customer_logout_redirect_sets_never_cache_headers(self):
        client = self._create_client(name="Logout Client", phone="01011113333")
        session = self.client.session
        session["customer_id"] = client.id
        session["customer_name"] = client.name
        session.save()

        response = self.client.get("/customer/logout/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/"))
        self._assert_never_cache_headers(response)

    @override_settings(
        DEBUG=True,
        STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    )
    def test_customer_form_age_input_blocks_negative_spinner_range(self):
        response = self.client.get("/customer/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_age"', html=False)
        self.assertContains(response, 'min="0"', html=False)

    def test_customer_form_rejects_empty_submission(self):
        response = self.client.post("/customer/", {})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "이름을 입력해 주세요.")
        self.assertIsNone(self.client.session.get("customer_id"))

    def test_customer_form_requires_privacy_agreement(self):
        response = self.client.post(
            "/customer/",
            {
                "name": "No Consent",
                "gender": "female",
                "age": "29",
                "phone": "010-5555-7777",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI 스타일 분석 데이터 수집 및 이용에 동의해 주세요.")
        self.assertIsNone(self.client.session.get("customer_id"))

    def test_partner_verify_rejects_legacy_pin_only_login(self):
        admin = self._create_admin(
            name="Owner Kim",
            store_name="MirrAI Salon",
            role="owner",
            phone="01099998888",
            business_number=build_valid_business_number("123456780"),
            password_hash=make_password("1234"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )

        response = self.client.post("/partner/verify/", {"pin": "1234"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "error")
        self.assertEqual(self.client.session.get("admin_id"), None)

    @override_settings(
        DEBUG=True,
        STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    )
    def test_partner_login_page_renders(self):
        response = self.client.get("/partner/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/api/v1/designers/")
        self.assertContains(response, "/partner/signup/")
        self.assertNotContains(response, "이지아")

    @override_settings(
        DEBUG=True,
        STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    )
    def test_result_page_renders_retry_and_consult_labels(self):
        client = self._create_client(name="Result Client", phone="01030304444")
        session = self.client.session
        session["customer_id"] = client.id
        session["customer_name"] = client.name
        session.save()

        response = self.client.get("/customer/recommendations/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/api/v1/analysis/retry-recommendations/")
        self.assertContains(response, 'id="retryBtn"', html=False)
        self.assertContains(response, 'id="directConsultBtn"', html=False)
        self.assertContains(response, 'id="saveBtn"', html=False)
        self.assertContains(response, "/customer/consultation/complete/")

    @override_settings(
        DEBUG=True,
        STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    )
    def test_partner_dashboard_renders_pin_gate_for_shop_only_session(self):
        admin = self._create_admin(
            name="Dashboard Owner",
            store_name="MirrAI Dashboard",
            role="owner",
            phone="01055556666",
            business_number=build_valid_business_number("923456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        self._set_admin_session(admin)

        response = self.client.get("/partner/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["is_shop_owner"])
        self.assertContains(response, 'data-admin-gate-scope="dashboard"', html=False)

    @override_settings(
        DEBUG=True,
        STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    )
    def test_partner_dashboard_enter_allows_dashboard_scope_only(self):
        admin = self._create_admin(
            name="Dashboard Owner",
            store_name="MirrAI Dashboard",
            role="owner",
            phone="01055556665",
            business_number=build_valid_business_number("922456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        self._set_admin_session(admin)

        enter_response = self.client.post("/partner/dashboard/enter/", {"pin": "0000", "scope": "dashboard"})
        dashboard_response = self.client.get("/partner/dashboard/")
        session = self.client.session

        self.assertEqual(enter_response.status_code, 200)
        self.assertEqual(enter_response.json()["status"], "success")
        self.assertEqual(enter_response.json()["redirect"], "/partner/dashboard/")
        self.assertTrue(session["owner_dashboard_allowed"])
        self.assertFalse(session.get("owner_mypage_allowed", False))
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertTrue(dashboard_response.context["is_shop_owner"])
        self.assertContains(dashboard_response, 'id="showReportBtn"', html=False)
        self.assertContains(dashboard_response, "assignCustomer(")

    def test_partner_dashboard_enter_requires_pin_reentry(self):
        admin = self._create_admin(
            name="Dashboard Owner",
            store_name="MirrAI Dashboard",
            role="owner",
            phone="01055556664",
            business_number=build_valid_business_number("921456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        self._set_admin_session(admin)

        response = self.client.post("/partner/dashboard/enter/", {"pin": "1111", "scope": "dashboard"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["message"], "보안키가 일치하지 않습니다.")

    def test_partner_dashboard_enter_allows_mypage_scope_only(self):
        admin = self._create_admin(
            name="Dashboard Owner",
            store_name="MirrAI Dashboard",
            role="owner",
            phone="01055556663",
            business_number=build_valid_business_number("920456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        self._set_admin_session(admin)

        enter_response = self.client.post("/partner/dashboard/enter/", {"pin": "0000", "scope": "mypage"})
        mypage_response = self.client.get("/partner/mypage/")
        session = self.client.session

        self.assertEqual(enter_response.status_code, 200)
        self.assertEqual(enter_response.json()["status"], "success")
        self.assertEqual(enter_response.json()["redirect"], "/partner/mypage/")
        self.assertTrue(session["owner_mypage_allowed"])
        self.assertFalse(session.get("owner_dashboard_allowed", False))
        self.assertEqual(mypage_response.status_code, 200)
        self.assertTrue(mypage_response.context["is_mypage_owner"])

    def test_partner_dashboard_enter_upgrades_plaintext_admin_pin(self):
        admin = self._create_admin(
            name="Dashboard Owner",
            store_name="MirrAI Dashboard",
            role="owner",
            phone="01055556662",
            business_number=build_valid_business_number("919456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        AdminAccount.objects.filter(backend_admin_id=admin.id).update(admin_pin="1234")
        self._set_admin_session(admin)

        response = self.client.post("/partner/dashboard/enter/", {"pin": "1234", "scope": "dashboard"})
        persisted_admin = AdminAccount.objects.get(backend_admin_id=admin.id)

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(persisted_admin.admin_pin, "1234")
        self.assertTrue(check_password("1234", persisted_admin.admin_pin))

    def test_partner_mypage_change_pin_hashes_new_value(self):
        admin = self._create_admin(
            name="Dashboard Owner",
            store_name="MirrAI Dashboard",
            role="owner",
            phone="01055556661",
            business_number=build_valid_business_number("918456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        self._set_admin_session(admin)

        response = self.client.post(
            "/partner/mypage/",
            {
                "action": "change_pin",
                "current_pin": "0000",
                "admin_pin": "2468",
            },
        )
        persisted_admin = AdminAccount.objects.get(backend_admin_id=admin.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertTrue(check_password("2468", persisted_admin.admin_pin))
        self.assertFalse(response.json()["is_default_admin_pin"])

    def test_partner_dashboard_redirects_designer_to_staff_dashboard(self):
        admin = self._create_admin(
            name="Dashboard Owner",
            store_name="MirrAI Dashboard",
            role="owner",
            phone="01055556667",
            business_number=build_valid_business_number("924456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(
            shop=admin,
            name="Designer Redirect",
            phone="01081112009",
            pin_hash=make_password("2468"),
        )
        self._set_admin_session(admin)
        self._set_designer_session(designer)

        response = self.client.get("/partner/dashboard/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/partner/staff/"))

    def test_partner_dashboard_redirects_unauthenticated_user_to_partner_login(self):
        response = self.client.get("/partner/dashboard/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/partner/"))

    @override_settings(
        DEBUG=True,
        STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    )
    def test_partner_staff_dashboard_renders_with_storewide_report_controls(self):
        admin = self._create_admin(
            name="Dashboard Owner",
            store_name="MirrAI Dashboard",
            role="owner",
            phone="01055556668",
            business_number=build_valid_business_number("925456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(
            shop=admin,
            name="Designer Staff",
            phone="01081112010",
            pin_hash=make_password("2468"),
        )
        self._set_admin_session(admin)
        self._set_designer_session(designer)

        response = self.client.get("/partner/staff/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="customerListBody"', html=False)
        self.assertContains(response, 'id="showReportBtn"', html=False)

    def test_partner_staff_dashboard_redirects_owner_to_owner_dashboard(self):
        admin = self._create_admin(
            name="Dashboard Owner",
            store_name="MirrAI Dashboard",
            role="owner",
            phone="01055556669",
            business_number=build_valid_business_number("926456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        self._set_admin_session(admin)

        response = self.client.get("/partner/staff/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/partner/"))

    @override_settings(
        DEBUG=True,
        STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    )
    def test_partner_routes_show_access_denied_for_customer_session(self):
        client = self._create_client(name="Customer Session", phone="01010109999")
        session = self.client.session
        session["customer_id"] = client.id
        session["customer_name"] = client.name
        session.save()

        login_response = self.client.get("/partner/")
        dashboard_response = self.client.get("/partner/dashboard/")
        staff_response = self.client.get("/partner/staff/")

        self.assertEqual(login_response.status_code, 302)
        self.assertIn("/customer/continue/?notice=partner_forbidden_customer", login_response["Location"])
        self.assertEqual(dashboard_response.status_code, 302)
        self.assertIn("/customer/continue/?notice=partner_forbidden_customer", dashboard_response["Location"])
        self.assertEqual(staff_response.status_code, 302)
        self.assertIn("/customer/continue/?notice=partner_forbidden_customer", staff_response["Location"])

    def test_customer_resume_redirects_to_camera_for_active_customer(self):
        client = self._create_client(name="Resume Customer", phone="01010107777")
        session = self.client.session
        session["customer_id"] = client.id
        session["customer_name"] = client.name
        session.save()

        response = self.client.get("/customer/continue/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/customer/menu/"))

    @override_settings(
        DEBUG=True,
        STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    )
    def test_customer_menu_page_renders_branching_options(self):
        client = self._create_client(name="Menu Customer", phone="01010106665")
        session = self.client.session
        session["customer_id"] = client.id
        session["customer_name"] = client.name
        session.save()

        response = self.client.get("/customer/menu/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/customer/history/")
        self.assertContains(response, "/customer/trend/")
        self.assertContains(response, "/customer/camera/")

    @override_settings(
        DEBUG=True,
        STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    )
    def test_customer_recommendation_history_page_renders_previous_actions(self):
        client = self._create_client(name="History Customer", phone="01010105555")
        session = self.client.session
        session["customer_id"] = client.id
        session["customer_name"] = client.name
        session.save()

        response = self.client.get("/customer/history/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="historyConsultBtn"', html=False)
        self.assertContains(response, "/customer/menu/")
        self.assertContains(response, "/customer/camera/")

    @override_settings(
        DEBUG=True,
        STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    )
    def test_customer_result_legacy_redirects_to_history(self):
        client = self._create_client(name="Legacy History Customer", phone="01010105556")
        session = self.client.session
        session["customer_id"] = client.id
        session["customer_name"] = client.name
        session.save()

        response = self.client.get("/customer/result/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/customer/history/", response["Location"])

    @override_settings(
        DEBUG=True,
        STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    )
    def test_customer_trend_page_renders_consultation_actions(self):
        client = self._create_client(name="Trend Customer", phone="01010106666")
        session = self.client.session
        session["customer_id"] = client.id
        session["customer_name"] = client.name
        session.save()

        response = self.client.get("/customer/trend/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="trendConsultBtn"', html=False)
        self.assertContains(response, "/customer/menu/")
        self.assertContains(response, "/customer/camera/")

    @override_settings(
        DEBUG=True,
        STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    )
    def test_customer_consultation_complete_page_renders_actions(self):
        client = self._create_client(name="Complete Customer", phone="01010107777")
        session = self.client.session
        session["customer_id"] = client.id
        session["customer_name"] = client.name
        session.save()

        response = self.client.get("/customer/consultation/complete/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "window.setInterval(")
        self.assertContains(response, "/customer/logout/")
        self.assertContains(response, "/customer/menu/")

    def test_partner_designer_management_page_renders_management_actions(self):
        admin = self._create_admin(
            name="Owner Manage",
            store_name="MirrAI Manage",
            role="owner",
            phone="01099887767",
            business_number=build_valid_business_number("733456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(
            shop=admin,
            name="Manage Designer",
            phone="01011113333",
            pin_hash=make_password("2468"),
        )
        self._set_admin_session(admin)

        response = self.client.get("/partner/designers/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/partner/designers/new/")
        self.assertContains(response, "/partner/designers/delete/")
        self.assertContains(response, "Manage Designer")

    def test_partner_designer_delete_page_deactivates_designer(self):
        admin = self._create_admin(
            name="Owner Delete",
            store_name="MirrAI Delete",
            role="owner",
            phone="01099887768",
            business_number=build_valid_business_number("743456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(
            shop=admin,
            name="Delete Designer",
            phone="01011114444",
            pin_hash=make_password("2468"),
        )
        self._set_admin_session(admin)

        response = self.client.post("/partner/designers/delete/", {"designer_id": designer.id})

        self.assertEqual(response.status_code, 302)
        self.assertIn("/partner/designers/?notice=designer_deleted", response["Location"])
        active_designer_ids = {item.id for item in get_designers_for_admin(admin=admin)}
        self.assertNotIn(designer.id, active_designer_ids)

    def test_partner_index_redirects_designer_session_to_staff_dashboard_with_notice(self):
        admin = self._create_admin(
            name="Owner",
            store_name="MirrAI",
            role="owner",
            phone="01010106666",
            business_number=build_valid_business_number("913456780"),
            password_hash=make_password("1234"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(
            shop=admin,
            name="Designer Redirect",
            phone="01020203333",
            pin_hash=make_password("2468"),
        )
        self._set_admin_session(admin)
        self._set_designer_session(designer)

        response = self.client.get("/partner/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/partner/staff/?notice=partner_forbidden_designer", response["Location"])

    def test_partner_verify_blocks_customer_session(self):
        client = self._create_client(name="Customer Session", phone="01010108888")
        session = self.client.session
        session["customer_id"] = client.id
        session["customer_name"] = client.name
        session.save()

        response = self.client.post("/partner/verify/", {"phone": "01012341234", "password": "pw1234!!"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["message"], "고객 세션을 종료한 뒤 파트너 로그인을 진행해 주세요.")

    def test_customer_logout_preserves_shop_session(self):
        admin = self._create_admin(
            name="Owner Keep",
            store_name="MirrAI Keep",
            role="owner",
            phone="01032104321",
            business_number=build_valid_business_number("823456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        client = self._create_client(name="Customer Keep", phone="01032109999")
        session = self.client.session
        session["admin_id"] = admin.id
        session["admin_name"] = admin.name
        session["customer_id"] = client.id
        session["customer_name"] = client.name
        session.save()

        response = self.client.get("/customer/logout/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/partner/"))
        self.assertEqual(self.client.session.get("admin_id"), admin.id)
        self.assertEqual(self.client.session.get("customer_id"), None)

    def test_customer_logout_redirects_main_page_when_no_partner_session_exists(self):
        client = self._create_client(name="Customer Only", phone="01032108888")
        session = self.client.session
        session["customer_id"] = client.id
        session["customer_name"] = client.name
        session.save()

        response = self.client.get("/customer/logout/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/"))
        self.assertEqual(self.client.session.get("customer_id"), None)

    def test_designer_logout_preserves_shop_session(self):
        admin = self._create_admin(
            name="Owner Keep",
            store_name="MirrAI Keep",
            role="owner",
            phone="01032104322",
            business_number=build_valid_business_number("823456781"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(
            shop=admin,
            name="Designer Keep",
            phone="01032105555",
            pin_hash=make_password("1234"),
        )
        self._set_admin_session(admin)
        self._set_designer_session(designer)

        response = self.client.get("/partner/staff/logout/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/partner/"))
        self.assertEqual(self.client.session.get("admin_id"), admin.id)
        self.assertEqual(self.client.session.get("designer_id"), None)

    def test_partner_staff_dashboard_redirects_unauthenticated_user_to_partner_login(self):
        response = self.client.get("/partner/staff/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/partner/"))

    def test_admin_panel_dashboard_redirects_to_partner_center(self):
        response = self.client.get("/admin-panel/dashboard/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/partner/"))

    def test_legacy_customer_list_returns_seeded_client_for_designer_scope(self):
        admin = self._create_admin(
            name="Owner Kim",
            store_name="MirrAI Salon",
            role="owner",
            phone="01055557777",
            business_number=build_valid_business_number("933456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(
            shop=admin,
            name="Designer One",
            phone="01081112001",
            pin_hash=make_password("2468"),
        )
        self._create_client(
            name="Client One",
            phone="01090001001",
            gender="female",
            shop=admin,
            designer=designer,
            age_input=28,
            birth_year_estimate=timezone.localdate().year - 28,
        )
        self._set_admin_session(admin)
        self._set_designer_session(designer)

        response = self.client.get("/api/v1/customers/", {"q": "Client One"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["name"], "Client One")

    def test_legacy_customer_list_excludes_unassigned_same_shop_clients_for_designer(self):
        admin = self._create_admin(
            name="Owner Kim",
            store_name="MirrAI Salon",
            role="owner",
            phone="01055557770",
            business_number=build_valid_business_number("932456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(
            shop=admin,
            name="Scoped Designer",
            phone="01081112003",
            pin_hash=make_password("2468"),
        )
        self._create_client(
            name="誘몃같??怨좉컼",
            phone="01090001007",
            gender="female",
            shop=admin,
            designer=None,
            assignment_source="shop_manual_assignment_pending",
        )
        self._set_admin_session(admin)
        self._set_designer_session(designer)

        response = self.client.get("/api/v1/customers/", {"q": "Pending"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 0)

    def test_legacy_customer_list_marks_assignment_pending_for_shop_session(self):
        admin = self._create_admin(
            name="Owner Kim",
            store_name="MirrAI Salon",
            role="owner",
            phone="01022223333",
            business_number=build_valid_business_number("963456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        self._create_client(
            name="誘몃같??怨좉컼",
            phone="01090001009",
            gender="female",
            shop=admin,
            assignment_source="shop_manual_assignment_pending",
        )
        self._set_admin_session(admin)

        response = self.client.get("/api/v1/customers/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["name"], "誘몃같??怨좉컼")
        self.assertEqual(payload[0]["designer_name"], None)
        self.assertEqual(payload[0]["assignment_source"], "shop_manual_assignment_pending")
        self.assertEqual(payload[0]["is_assignment_pending"], True)

    def test_legacy_trend_report_returns_summary_and_distribution(self):
        admin = self._create_admin(
            name="Trend Owner",
            store_name="MirrAI Trends",
            role="owner",
            phone="01055558888",
            business_number=build_valid_business_number("943456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(
            shop=admin,
            name="?몃젋???붿옄?대꼫",
            phone="01082222001",
            pin_hash=make_password("1357"),
        )
        client = self._create_client(
            name="?몃젋??怨좉컼",
            phone="01093334444",
            gender="female",
            shop=admin,
            designer=designer,
            age_input=25,
            birth_year_estimate=timezone.localdate().year - 25,
        )
        _, rows = self._seed_generated_batch(client=client)
        confirm_style_selection(
            client=client,
            recommendation_id=int(rows[0].id),
            source="current_recommendations",
        )
        self._set_admin_session(admin)

        response = self.client.get("/api/v1/analysis/report/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("summary", payload)
        self.assertIn("visitor_stats", payload)
        self.assertIn("style_distribution", payload)
        self.assertEqual(payload["summary"]["total_customers"], 1)

    def test_legacy_trend_report_is_available_in_designer_session(self):
        admin = self._create_admin(
            name="Store Owner",
            store_name="MirrAI Store",
            role="owner",
            phone="01055559999",
            business_number=build_valid_business_number("953456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer_a = self._create_designer(
            shop=admin,
            name="源誘몃굹",
            phone="01081112001",
            pin_hash=make_password("2468"),
        )
        designer_b = self._create_designer(
            shop=admin,
            name="諛뺤?",
            phone="01081112002",
            pin_hash=make_password("1357"),
        )
        client_a = self._create_client(
            name="Trend Client A",
            phone="01090001001",
            gender="female",
            shop=admin,
            designer=designer_a,
            age_input=28,
            birth_year_estimate=timezone.localdate().year - 28,
        )
        client_b = self._create_client(
            name="Trend Client B",
            phone="01090001003",
            gender="female",
            shop=admin,
            designer=designer_b,
            age_input=24,
            birth_year_estimate=timezone.localdate().year - 24,
        )
        _, rows_a = self._seed_generated_batch(client=client_a)
        _, rows_b = self._seed_generated_batch(client=client_b)
        confirm_style_selection(
            client=client_a,
            recommendation_id=int(rows_a[0].id),
            source="current_recommendations",
        )
        confirm_style_selection(
            client=client_b,
            recommendation_id=int(rows_b[0].id),
            source="current_recommendations",
        )
        self._set_admin_session(admin)
        self._set_designer_session(designer_a)

        response = self.client.get("/api/v1/analysis/report/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("summary", payload)
        self.assertIn("style_distribution", payload)
        self.assertEqual(payload["summary"]["total_customers"], 2)

    def test_partner_verify_accepts_phone_and_password_for_shop_login(self):
        admin = self._create_admin(
            name="Owner Shop",
            store_name="MirrAI Shop",
            role="owner",
            phone="01012344321",
            business_number=build_valid_business_number("223456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )

        response = self.client.post(
            "/partner/verify/",
            {
                "phone": admin.phone,
                "password": "pw1234!!",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["session_type"], "admin")
        self.assertEqual(payload["next_step"], "designer_select")
        self.assertEqual(payload["legacy_shop_id"], get_legacy_admin_id(admin=admin))
        self.assertEqual(self.client.session.get("admin_id"), admin.id)
        self.assertEqual(self.client.session.get("admin_legacy_id"), get_legacy_admin_id(admin=admin))

    def test_partner_verify_clears_customer_session_when_designer_logs_in(self):
        admin = self._create_admin(
            name="Owner Shop",
            store_name="MirrAI Shop",
            role="owner",
            phone="01012344322",
            business_number=build_valid_business_number("223456781"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(
            shop=admin,
            name="Designer Login",
            phone="01044443335",
            pin_hash=make_password("1234"),
        )
        client = self._create_client(name="Existing Client", phone="01020002000")
        session = self.client.session
        session["admin_id"] = admin.id
        session["admin_name"] = admin.name
        session["customer_id"] = client.id
        session["customer_name"] = client.name
        session.save()

        response = self.client.post(
            "/partner/verify/",
            {
                "pin": "1234",
                "designer_id": designer.id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session.get("customer_id"), None)

    def test_partner_verify_rejects_business_number_login_for_shop(self):
        admin = self._create_admin(
            name="Owner Shop",
            store_name="MirrAI Shop",
            role="owner",
            phone="01012344323",
            business_number=build_valid_business_number("223456782"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )

        response = self.client.post(
            "/partner/verify/",
            {
                "biz_number": admin.business_number,
                "password": "pw1234!!",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], "매장 로그인은 관리자 연락처와 비밀번호로 진행해 주세요.")

    def test_partner_verify_requires_phone_and_password_for_shop_login(self):
        response = self.client.post("/partner/verify/", {})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], "연락처와 비밀번호를 입력해 주세요.")

    def test_partner_verify_accepts_designer_pin_after_shop_login(self):
        admin = self._create_admin(
            name="Owner Kim",
            store_name="MirrAI Salon",
            role="owner",
            phone="01099997777",
            business_number=build_valid_business_number("123456781"),
            password_hash=make_password("9999"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(
            shop=admin,
            name="Designer Lee",
            phone="01044443333",
            pin_hash=make_password("1234"),
        )
        self._set_admin_session(admin)

        response = self.client.post(
            "/partner/verify/",
            {"pin": "1234", "designer_id": designer.id},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["session_type"], "designer")
        self.assertEqual(payload["redirect"], "/partner/staff/")
        self.assertEqual(payload["legacy_shop_id"], get_legacy_admin_id(admin=admin))
        self.assertEqual(payload["legacy_designer_id"], get_legacy_designer_id(designer=designer))
        self.assertEqual(self.client.session.get("admin_id"), admin.id)
        self.assertEqual(self.client.session.get("admin_legacy_id"), get_legacy_admin_id(admin=admin))
        self.assertEqual(self.client.session.get("designer_id"), designer.id)
        self.assertEqual(self.client.session.get("designer_legacy_id"), get_legacy_designer_id(designer=designer))

    def test_partner_verify_requires_shop_session_before_designer_pin_login(self):
        admin = self._create_admin(
            name="Owner Kim",
            store_name="MirrAI Salon",
            role="owner",
            phone="01099997770",
            business_number=build_valid_business_number("123456784"),
            password_hash=make_password("9999"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(
            shop=admin,
            name="Designer Lee",
            phone="01044443334",
            pin_hash=make_password("1234"),
        )

        response = self.client.post(
            "/partner/verify/",
            {"pin": "1234", "designer_id": designer.id},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["status"], "error")
        self.assertEqual(self.client.session.get("designer_id"), None)

    def test_partner_verify_scopes_designer_login_to_active_shop(self):
        admin = self._create_admin(
            name="Scoped Owner",
            store_name="MirrAI Scoped",
            role="owner",
            phone="01099996666",
            business_number=build_valid_business_number("123456782"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        other_admin = self._create_admin(
            name="Other Owner",
            store_name="Other Shop",
            role="owner",
            phone="01099995555",
            business_number=build_valid_business_number("123456783"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        wrong_designer = self._create_designer(
            shop=other_admin,
            name="Wrong Designer",
            phone="01011112222",
            pin_hash=make_password("1234"),
        )
        self._set_admin_session(admin)

        response = self.client.post(
            "/partner/verify/",
            {"pin": "1234", "designer_id": wrong_designer.id},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.session.get("designer_id"), None)

    def test_partner_designer_list_returns_only_active_shop_designers(self):
        admin = self._create_admin(
            name="Owner Kim",
            store_name="MirrAI Salon",
            role="owner",
            phone="01033334445",
            business_number=build_valid_business_number("523456780"),
            password_hash=make_password("1234"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        other_admin = self._create_admin(
            name="Owner Park",
            store_name="Other Salon",
            role="owner",
            phone="01033334446",
            business_number=build_valid_business_number("523456781"),
            password_hash=make_password("1234"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        self._create_designer(shop=admin, name="Designer A", pin_hash=make_password("1234"))
        self._create_designer(shop=admin, name="Designer B", pin_hash=make_password("5678"))
        self._create_designer(shop=other_admin, name="Designer C", pin_hash=make_password("9999"))
        self._set_admin_session(admin)

        response = self.client.get("/api/v1/designers/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 2)
        self.assertEqual({item["name"] for item in payload}, {"Designer A", "Designer B"})
        self.assertTrue(all("profile_image" in item for item in payload))

    def test_partner_designer_list_blocks_designer_session(self):
        admin = self._create_admin(
            name="Owner Kim",
            store_name="MirrAI Salon",
            role="owner",
            phone="01033334440",
            business_number=build_valid_business_number("513456780"),
            password_hash=make_password("1234"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(shop=admin, name="Designer A", pin_hash=make_password("1234"))
        self._set_admin_session(admin)
        self._set_designer_session(designer)

        response = self.client.get("/api/v1/designers/")

        self.assertEqual(response.status_code, 403)

    def test_partner_designer_list_requires_shop_session(self):
        response = self.client.get("/api/v1/designers/")

        self.assertEqual(response.status_code, 401)

    def test_shop_can_manually_assign_pending_client_to_designer(self):
        admin = self._create_admin(
            name="Owner Kim",
            store_name="MirrAI Salon",
            role="owner",
            phone="01033334447",
            business_number=build_valid_business_number("533456780"),
            password_hash=make_password("1234"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(shop=admin, name="Designer A", pin_hash=make_password("1234"))
        client = self._create_client(
            name="誘몃같??怨좉컼",
            phone="01090002001",
            shop=admin,
            assignment_source="shop_manual_assignment_pending",
        )
        self._set_admin_session(admin)

        response = self.client.post(
            f"/api/v1/customers/{client.id}/assign/",
            {"designer_id": designer.id},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        client.refresh_from_db()
        self.assertEqual(client.designer_id, designer.id)
        self.assertEqual(client.assignment_source, "shop_manual_assignment")
        self.assertIsNotNone(client.assigned_at)

    def test_shop_can_reassign_existing_client_to_another_designer(self):
        admin = self._create_admin(
            name="Owner Kim",
            store_name="MirrAI Salon",
            role="owner",
            phone="01033334449",
            business_number=build_valid_business_number("553456780"),
            password_hash=make_password("1234"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer_a = self._create_designer(shop=admin, name="Designer A", pin_hash=make_password("1234"))
        designer_b = self._create_designer(shop=admin, name="Designer B", pin_hash=make_password("5678"))
        client = self._create_client(
            name="湲곕같??怨좉컼",
            phone="01090002003",
            shop=admin,
            designer=designer_a,
            assigned_at=timezone.now(),
            assignment_source="seeded_designer",
        )
        self._set_admin_session(admin)

        response = self.client.post(
            f"/api/v1/customers/{client.id}/assign/",
            {"designer_id": designer_b.id},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        client.refresh_from_db()
        self.assertEqual(client.designer_id, designer_b.id)
        self.assertEqual(client.assignment_source, "shop_manual_assignment")
        self.assertIsNotNone(client.assigned_at)

    def test_designer_session_cannot_manually_assign_client(self):
        admin = self._create_admin(
            name="Owner Kim",
            store_name="MirrAI Salon",
            role="owner",
            phone="01033334448",
            business_number=build_valid_business_number("543456780"),
            password_hash=make_password("1234"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(shop=admin, name="Designer A", pin_hash=make_password("1234"))
        client = self._create_client(
            name="誘몃같??怨좉컼",
            phone="01090002002",
            shop=admin,
            assignment_source="shop_manual_assignment_pending",
        )
        self._set_admin_session(admin)
        self._set_designer_session(designer)

        response = self.client.post(
            f"/api/v1/customers/{client.id}/assign/",
            {"designer_id": designer.id},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        original_designer_id = client.designer_id
        client.refresh_from_db()
        self.assertEqual(client.designer_id, original_designer_id)

    def test_partner_signup_page_post_creates_admin_and_redirects(self):
        valid_business_number = build_valid_business_number("623456780")

        response = self.client.post(
            "/partner/signup/",
            {
                "name": "Owner Moon",
                "store_name": "MirrAI Moon",
                "phone": "010-8888-1111",
                "business_number": valid_business_number,
                "password": "pw1234!!",
                "password_confirm": "pw1234!!",
                "agree_terms": "on",
                "agree_privacy": "on",
                "agree_third_party_sharing": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/partner/dashboard/"))
        admin = self._get_admin_by_phone("01088881111")
        self.assertEqual(admin.business_number, valid_business_number)
        self.assertIsNotNone(self.client.session.get("admin_id"))

    def test_partner_signup_page_rejects_non_mobile_admin_phone(self):
        valid_business_number = build_valid_business_number("623456781")

        response = self.client.post(
            "/partner/signup/",
            {
                "name": "Owner Landline",
                "store_name": "MirrAI Landline",
                "phone": "02-123-4567",
                "business_number": valid_business_number,
                "password": "pw1234!!",
                "password_confirm": "pw1234!!",
                "agree_terms": "on",
                "agree_privacy": "on",
                "agree_third_party_sharing": "on",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "관리자 연락처는 휴대폰 번호(010-0000-0000)로 입력해 주세요.")
        self.assertIsNone(self._get_admin_by_phone("021234567"))

    def test_partner_signup_page_accepts_biz_number_alias(self):
        valid_business_number = build_valid_business_number("723456780")

        response = self.client.post(
            "/partner/signup/",
            {
                "name": "Owner Alias",
                "store_name": "MirrAI Alias",
                "phone": "010-7777-1111",
                "biz_number": valid_business_number,
                "password": "pw1234!!",
                "password_confirm": "pw1234!!",
                "agree_terms": "on",
                "agree_privacy": "on",
                "agree_third_party_sharing": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/partner/dashboard/"))
        admin = self._get_admin_by_phone("01077771111")
        self.assertEqual(admin.business_number, valid_business_number)

    @override_settings(
        DEBUG=True,
        STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    )
    def test_partner_signup_page_rejects_password_confirmation_mismatch(self):
        valid_business_number = build_valid_business_number("823456780")

        response = self.client.post(
            "/partner/signup/",
            {
                "name": "Owner Mismatch",
                "store_name": "MirrAI Mismatch",
                "phone": "010-6666-1111",
                "business_number": valid_business_number,
                "password": "pw1234!!",
                "password_confirm": "pw0000!!",
                "agree_terms": "on",
                "agree_privacy": "on",
                "agree_third_party_sharing": "on",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "비밀번호 확인이 일치하지 않습니다.", status_code=400)

    def test_register_admin_shows_field_specific_required_message(self):
        with self.assertRaisesMessage(ValueError, "대표자 성함은 필수 정보입니다."):
            register_admin(
                payload={
                    "name": "",
                    "store_name": "MirrAI Missing",
                    "phone": "010-6666-1111",
                    "business_number": build_valid_business_number("833456780"),
                    "password": "pw1234!!",
                    "agree_terms": True,
                    "agree_privacy": True,
                    "agree_third_party_sharing": True,
                }
            )

    def test_partner_designer_signup_page_creates_designer_for_owner_shop(self):
        admin = self._create_admin(
            name="Owner Create",
            store_name="MirrAI Create",
            role="owner",
            phone="01099887766",
            business_number=build_valid_business_number("633456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        self._set_admin_session(admin)

        response = self.client.post(
            "/partner/designers/new/",
            {
                "name": "New Designer",
                "phone": "010-1111-2222",
                "pin": "2580",
                "pin_confirm": "2580",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/partner/?notice=designer_created", response["Location"])
        designer = next(item for item in get_designers_for_admin(admin=admin) if item.phone == "01011112222")
        self.assertEqual(designer.name, "New Designer")

    def test_partner_designer_signup_page_rejects_designer_session(self):
        admin = self._create_admin(
            name="Owner Block",
            store_name="MirrAI Block",
            role="owner",
            phone="01077889900",
            business_number=build_valid_business_number("643456780"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(
            shop=admin,
            name="Existing Designer",
            phone="01033334444",
            pin_hash=make_password("2468"),
        )
        self._set_admin_session(admin)
        self._set_designer_session(designer)

        response = self.client.get("/partner/designers/new/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/partner/"))

    def test_customer_form_auto_assigns_single_designer_for_shop_session(self):
        admin = self._create_admin(
            name="Owner Kim",
            store_name="MirrAI Salon",
            role="owner",
            phone="01022223333",
            business_number=build_valid_business_number("323456780"),
            password_hash=make_password("1234"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(
            shop=admin,
            name="Solo Designer",
            phone="01088889999",
            pin_hash=make_password("1111"),
        )
        self._set_admin_session(admin)

        response = self.client.post(
            "/customer/",
            {
                "name": "Assigned User",
                "gender": "female",
                "age": "31",
                "phone": "010-2020-3030",
                "agree_privacy": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        client = self._get_client_by_phone("01020203030")
        self.assertEqual(client.shop_id, admin.id)
        self.assertEqual(client.designer_id, designer.id)
        self.assertEqual(client.assignment_source, "auto_single_designer")

    def test_customer_form_keeps_shop_owned_assignment_when_no_designer_exists(self):
        admin = self._create_admin(
            name="Head Owner",
            store_name="MirrAI Head",
            role="owner",
            phone="01022224444",
            business_number=build_valid_business_number("333456780"),
            password_hash=make_password("1234"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        self._set_admin_session(admin)

        response = self.client.post(
            "/customer/",
            {
                "name": "Shop Owned User",
                "gender": "female",
                "age": "29",
                "phone": "010-2020-4040",
                "agree_privacy": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        client = self._get_client_by_phone("01020204040")
        self.assertEqual(client.shop_id, admin.id)
        self.assertIsNone(client.designer_id)
        self.assertEqual(client.assignment_source, "auto_shop_only")
        self.assertIsNotNone(client.assigned_at)

    def test_customer_form_leaves_client_unassigned_when_multiple_designers_exist(self):
        admin = self._create_admin(
            name="Multi Owner",
            store_name="MirrAI Multi",
            role="owner",
            phone="01022225555",
            business_number=build_valid_business_number("343456780"),
            password_hash=make_password("1234"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        self._create_designer(shop=admin, name="Designer A", phone="01088881111", pin_hash=make_password("1111"))
        self._create_designer(shop=admin, name="Designer B", phone="01088882222", pin_hash=make_password("2222"))
        self._set_admin_session(admin)

        response = self.client.post(
            "/customer/",
            {
                "name": "Manual Queue User",
                "gender": "male",
                "age": "33",
                "phone": "010-2020-5050",
                "agree_privacy": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        client = self._get_client_by_phone("01020205050")
        self.assertEqual(client.shop_id, admin.id)
        self.assertIsNone(client.designer_id)
        self.assertEqual(client.assignment_source, "shop_manual_assignment_pending")
        self.assertIsNone(client.assigned_at)

    def test_admin_register_api_sets_session_and_redirect(self):
        response = self.client.post(
            "/api/v1/admin/auth/register/",
            {
                "name": "Owner Park",
                "store_name": "MirrAI New",
                "role": "owner",
                "phone": "01066667777",
                "business_number": build_valid_business_number("423456780"),
                "password": "pw1234!!",
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
                "agree_marketing": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["redirect"], "/partner/dashboard/")
        self.assertEqual(response.json()["session_type"], "admin")
        self.assertIn("legacy_admin_id", response.json())
        self.assertIsNotNone(self.client.session.get("admin_id"))

    def test_admin_login_api_returns_legacy_admin_identifier(self):
        admin = self._create_admin(
            name="Login Owner",
            store_name="MirrAI Login",
            role="owner",
            phone="01066667770",
            business_number=build_valid_business_number("423456783"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )

        response = self.client.post(
            "/api/v1/admin/auth/login/",
            {
                "phone": "01066667770",
                "password": "pw1234!!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["admin"]["admin_id"], admin.id)
        self.assertEqual(payload["legacy_admin_id"], get_legacy_admin_id(admin=admin))

    def test_client_login_api_returns_legacy_client_identifier(self):
        client = self._create_client(name="Legacy Login Client", phone="01012344321")

        response = self.client.post(
            "/api/v1/auth/login/",
            {"phone": "01012344321"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["client_id"], client.id)
        self.assertEqual(payload["legacy_client_id"], get_legacy_client_id(client=client))

    def test_admin_refresh_api_accepts_legacy_admin_id_when_canonical_id_is_stale(self):
        admin = self._create_admin(
            name="Refresh Owner",
            store_name="MirrAI Refresh",
            role="owner",
            phone="01066667771",
            business_number=build_valid_business_number("423456784"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        refresh_token = signing.dumps(
            {
                "type": "admin",
                "token_kind": "refresh",
                "admin_id": admin.id + 9999,
                "legacy_admin_id": get_legacy_admin_id(admin=admin),
            },
            key=settings.SECRET_KEY,
            salt=ADMIN_REFRESH_TOKEN_SALT,
            compress=True,
        )

        response = self.client.post(
            "/api/v1/admin/auth/refresh/",
            {"refresh_token": refresh_token},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["admin_id"], admin.id)
        self.assertEqual(payload["legacy_admin_id"], get_legacy_admin_id(admin=admin))
        self.assertIn("access_token", payload)

    def test_client_refresh_api_accepts_legacy_client_id_when_canonical_id_is_stale(self):
        client = self._create_client(name="Refresh Client", phone="01012344322")
        refresh_token = signing.dumps(
            {
                "type": "client",
                "token_kind": "refresh",
                "client_id": client.id + 9999,
                "legacy_client_id": get_legacy_client_id(client=client),
            },
            key=settings.SECRET_KEY,
            salt=CLIENT_REFRESH_TOKEN_SALT,
            compress=True,
        )

        response = self.client.post(
            "/api/v1/auth/refresh/",
            {"refresh_token": refresh_token},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["client_id"], client.id)
        self.assertEqual(payload["legacy_client_id"], get_legacy_client_id(client=client))
        self.assertIn("access_token", payload)

    def test_admin_bearer_token_auth_accepts_legacy_admin_id_when_canonical_id_is_stale(self):
        admin = self._create_admin(
            name="Bearer Owner",
            store_name="MirrAI Bearer",
            role="owner",
            phone="01066667772",
            business_number=build_valid_business_number("423456785"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        access_token = signing.dumps(
            {
                "type": "admin",
                "token_kind": "access",
                "admin_id": admin.id + 9999,
                "legacy_admin_id": get_legacy_admin_id(admin=admin),
                "role": admin.role,
                "store_name": admin.store_name,
            },
            key=settings.SECRET_KEY,
            salt=ADMIN_ACCESS_TOKEN_SALT,
            compress=True,
        )

        response = self.client.get(
            "/api/v1/admin/auth/me/",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["admin"]["admin_id"], admin.id)
        self.assertEqual(payload["admin"]["legacy_admin_id"], get_legacy_admin_id(admin=admin))

    def test_admin_register_api_returns_field_errors_for_duplicate_phone(self):
        self._create_admin(
            name="Existing Owner",
            store_name="MirrAI Existing",
            role="owner",
            phone="01066667777",
            business_number=build_valid_business_number("423456781"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )

        response = self.client.post(
            "/api/v1/admin/auth/register/",
            {
                "name": "Owner Park",
                "store_name": "MirrAI New",
                "role": "owner",
                "phone": "01066667777",
                "business_number": build_valid_business_number("423456780"),
                "password": "pw1234!!",
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
                "agree_marketing": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error_code"], "validation_error")
        self.assertIn("errors", payload)
        self.assertIn("phone", payload["errors"])
        self.assertEqual(payload["errors"]["phone"][0], "이미 등록된 관리자 연락처입니다.")

    def test_admin_register_api_returns_field_errors_for_missing_required_agreement(self):
        response = self.client.post(
            "/api/v1/admin/auth/register/",
            {
                "name": "Owner Park",
                "store_name": "MirrAI New",
                "role": "owner",
                "phone": "01066667778",
                "business_number": build_valid_business_number("423456782"),
                "password": "pw1234!!",
                "agree_terms": False,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
                "agree_marketing": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error_code"], "validation_error")
        self.assertIn("errors", payload)
        self.assertIn("agree_terms", payload["errors"])

    def test_admin_login_api_returns_non_field_errors_on_invalid_credentials(self):
        response = self.client.post(
            "/api/v1/admin/auth/login/",
            {
                "phone": "01000001111",
                "password": "wrong-password",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error_code"], "validation_error")
        self.assertIn("errors", payload)
        self.assertIn("non_field_errors", payload["errors"])

    def test_recommendation_endpoint_accepts_customer_id_and_returns_legacy_array(self):
        client = self._create_client(name="Legacy Client", phone="01033334444")
        self._seed_generated_batch(client=client)

        response = self.client.get(f"/api/v1/analysis/recommendations/?customer_id={client.id}")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        self.assertGreaterEqual(len(response.json()), 1)
        self.assertIn("reference_images", response.json()[0])

    def test_capture_upload_accepts_customer_id_alias(self):
        client = self._create_client(name="Capture Alias", phone="01077776666")
        buffer = io.BytesIO()
        Image.new("RGB", (640, 640), "white").save(buffer, format="PNG")

        upload = SimpleUploadedFile("capture.png", buffer.getvalue(), content_type="image/png")

        response = self.client.post(
            "/api/v1/capture/upload/",
            {
                "customer_id": str(client.id),
                "file": upload,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("status", payload)
        self.assertIn("storage_snapshot", payload)
        self.assertIn(payload["storage_snapshot"]["storage_mode"], {"local", "remote"})
        self.assertEqual(payload["storage_snapshot"]["bucket_name"], "mirrai-assets")
        self.assertFalse(payload["storage_snapshot"]["has_required_capture_assets"])

    def test_capture_status_returns_storage_snapshot_and_resolution_status(self):
        client = self._create_client(name="Capture Status", phone="01010101010")
        record = create_legacy_capture_upload_record(
            client=client,
            original_path="captures/original.jpg",
            processed_path="captures/processed.jpg",
            deidentified_path="captures/deidentified.jpg",
            filename="capture.jpg",
            status="DONE",
            face_count=1,
            privacy_snapshot={"storage_policy": "asset_store"},
            landmark_snapshot={"version": "coarse-v1"},
            error_note=None,
        )

        response = self.client.get(f"/api/v1/capture/status/?record_id={record.id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("storage_snapshot", payload)
        self.assertEqual(payload["storage_snapshot"]["path_count"], 3)
        self.assertIn("resolution_statuses", payload["storage_snapshot"])
        self.assertIn("reference_presence", payload["storage_snapshot"])
        self.assertTrue(payload["storage_snapshot"]["reference_presence"]["original_path"])

    def test_survey_endpoint_accepts_customer_hidden_field_alias(self):
        client = self._create_client(name="Survey Alias", phone="01012121212")

        response = self.client.post(
            "/api/v1/survey/",
            {
                "customer": client.id,
                "target_length": "short",
                "target_vibe": "soft",
                "scalp_type": "normal",
                "hair_colour": "black",
                "budget_range": "10-15",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        survey = get_latest_survey(client)
        self.assertEqual(survey.target_length, "short")
        self.assertEqual(survey.target_vibe, "soft")

    def test_survey_endpoint_maps_male_q1_to_q6_answers(self):
        client = self._create_client(name="Male Survey", phone="01012120001", gender="male")

        response = self.client.post(
            "/api/v1/survey/",
            {
                "customer": client.id,
                "q1": "아주 짧고 깔끔하게",
                "q2": "단정한",
                "q3": "펌 없이 깔끔하게",
                "q4": "가르마 스타일 선호",
                "q5": "자연스러운 볼륨 정도",
                "q6": "트렌디한",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        survey = get_latest_survey(client)
        self.assertEqual(survey.target_length, "short")
        self.assertEqual(survey.target_vibe, "chic")
        self.assertEqual(survey.scalp_type, "waved")
        self.assertEqual(survey.hair_colour, "unknown")
        self.assertEqual(survey.budget_range, "unknown")
        self.assertTrue(any(survey.preference_vector))

    def test_survey_endpoint_maps_female_q1_to_q6_answers(self):
        client = self._create_client(name="Female Survey", phone="01012120002", gender="female")

        response = self.client.post(
            "/api/v1/survey/",
            {
                "customer": client.id,
                "q1": "길게",
                "q2": "길이감 있는 스타일",
                "q3": "레이어드컷",
                "q4": "끝선 위주 자연스러운 컬",
                "q5": "고급스러운",
                "q6": "전체적으로 웨이브감",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        survey = get_latest_survey(client)
        self.assertEqual(survey.target_length, "long")
        self.assertEqual(survey.target_vibe, "elegant")
        self.assertEqual(survey.scalp_type, "waved")
        self.assertEqual(survey.hair_colour, "unknown")
        self.assertEqual(survey.budget_range, "unknown")
        self.assertTrue(any(survey.preference_vector))

    def test_legacy_admin_customer_and_report_endpoints_work_with_session(self):
        admin = self._create_admin(
            name="Session Admin",
            store_name="MirrAI Session",
            role="owner",
            phone="01055554444",
            business_number=build_valid_business_number("234567890"),
            password_hash=make_password("1234"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        client = self._create_client(name="Admin View Client", phone="01011112222")
        _, rows = self._seed_generated_batch(client=client, target_length="medium", target_vibe="chic")
        confirm_style_selection(
            client=client,
            recommendation_id=int(rows[0].id),
            source="current_recommendations",
        )

        self._set_admin_session(admin)

        list_response = self.client.get("/api/v1/customers/")
        detail_response = self.client.get(f"/api/v1/customers/{client.id}/")
        report_response = self.client.get("/api/v1/analysis/report/")

        self.assertEqual(list_response.status_code, 200)
        self.assertIsInstance(list_response.json(), list)
        self.assertEqual(detail_response.status_code, 200)
        self.assertIn("survey", detail_response.json())
        self.assertIn("face_analyses", detail_response.json())
        self.assertIn("captures", detail_response.json())
        self.assertEqual(report_response.status_code, 200)
        self.assertIn("summary", report_response.json())
        self.assertIn("visitor_stats", report_response.json())
        self.assertIn("style_distribution", report_response.json())

    def test_legacy_admin_customer_detail_accepts_legacy_client_identifier(self):
        admin = self._create_admin(
            name="Session Admin",
            store_name="MirrAI Session",
            role="owner",
            phone="01056565656",
            business_number=build_valid_business_number("334567890"),
            password_hash=make_password("1234"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        client = self._create_client(name="Legacy Route Client", phone="01022223333", shop=admin)

        self._set_admin_session(admin)

        response = self.client.get(f"/api/v1/customers/{get_legacy_client_id(client=client)}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], client.id)
        self.assertEqual(response.json()["legacy_client_id"], get_legacy_client_id(client=client))

    def test_designer_list_exposes_legacy_designer_identifier(self):
        admin = self._create_admin(
            name="Owner Designers",
            store_name="MirrAI Designers",
            role="owner",
            phone="01045454545",
            business_number=build_valid_business_number("634567890"),
            password_hash=make_password("pw1234!!"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(
            shop=admin,
            name="Legacy Designer",
            phone="01077770000",
            pin_hash=make_password("2468"),
        )
        self._set_admin_session(admin)

        response = self.client.get("/api/v1/admin/designers/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        row = next(item for item in payload if item["id"] == designer.id)
        self.assertEqual(row["legacy_id"], get_legacy_designer_id(designer=designer))

    def test_legacy_admin_customer_and_report_endpoints_scope_to_designer_session(self):
        admin = self._create_admin(
            name="Shop Owner",
            store_name="MirrAI Team",
            role="owner",
            phone="01077778888",
            business_number=build_valid_business_number("523456780"),
            password_hash=make_password("4321"),
            consent_snapshot={
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
            },
        )
        designer = self._create_designer(
            shop=admin,
            name="Scoped Designer",
            pin_hash=make_password("4567"),
        )
        own_client = self._create_client(name="Own Client", phone="01055550001", shop=admin, designer=designer)
        other_client = self._create_client(name="Other Client", phone="01055550002", shop=admin)
        _, own_rows = self._seed_generated_batch(client=own_client)
        _, other_rows = self._seed_generated_batch(client=other_client)
        confirm_style_selection(
            client=own_client,
            recommendation_id=int(own_rows[0].id),
            source="current_recommendations",
        )
        confirm_style_selection(
            client=other_client,
            recommendation_id=int(other_rows[0].id),
            source="current_recommendations",
        )

        self._set_designer_session(designer)

        list_response = self.client.get("/api/v1/customers/")
        report_response = self.client.get("/api/v1/analysis/report/")

        self.assertEqual(list_response.status_code, 200)
        payload = list_response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual({item["id"] for item in payload}, {own_client.id})
        self.assertEqual(report_response.status_code, 200)
        self.assertEqual(report_response.json()["summary"]["total_customers"], 1)


