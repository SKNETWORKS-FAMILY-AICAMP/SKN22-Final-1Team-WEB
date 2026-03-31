import io
import shutil
import tempfile

from django.contrib.auth.hashers import make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from app.api.v1.services_django import persist_generated_batch
from app.models_django import AdminAccount, CaptureRecord, Client, Designer, FaceAnalysis, StyleSelection, Survey


def build_valid_business_number(prefix: str = "123456789") -> str:
    digits = [int(char) for char in prefix]
    weights = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    checksum = sum(digit * weight for digit, weight in zip(digits, weights))
    checksum += (digits[8] * 5) // 10
    check_digit = (10 - (checksum % 10)) % 10
    return prefix + str(check_digit)


@override_settings(SUPABASE_USE_REMOTE_STORAGE=False)
class FrontCompatibilityTests(APITestCase):
    def setUp(self):
        self.temp_media_root = tempfile.mkdtemp(prefix="mirrai-front-compat-")
        self.media_override = override_settings(MEDIA_ROOT=self.temp_media_root)
        self.media_override.enable()

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.temp_media_root, ignore_errors=True)

    def _set_admin_session(self, admin):
        session = self.client.session
        session["admin_id"] = admin.id
        session["admin_name"] = admin.name
        session.save()

    def _set_designer_session(self, designer):
        session = self.client.session
        session["designer_id"] = designer.id
        session["designer_name"] = designer.name
        session["admin_id"] = designer.shop_id
        session["admin_name"] = designer.shop.name
        session.save()

    def test_customer_form_post_creates_session_and_redirects(self):
        response = self.client.post(
            "/customer/",
            {
                "name": "Kim User",
                "age": "27",
                "phone": "010-1234-5678",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/customer/survey/"))
        session = self.client.session
        self.assertIsNotNone(session.get("customer_id"))
        self.assertEqual(session.get("customer_name"), "Kim User")

    def test_partner_verify_sets_admin_session(self):
        admin = AdminAccount.objects.create(
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

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(self.client.session.get("admin_id"), admin.id)
        self.assertEqual(response.json()["session_type"], "admin")

    def test_partner_verify_accepts_designer_pin_and_sets_designer_session(self):
        admin = AdminAccount.objects.create(
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
        designer = Designer.objects.create(
            shop=admin,
            name="Designer Lee",
            phone="01044443333",
            pin_hash=make_password("1234"),
        )

        response = self.client.post("/partner/verify/", {"pin": "1234"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["session_type"], "designer")
        self.assertEqual(self.client.session.get("admin_id"), admin.id)
        self.assertEqual(self.client.session.get("designer_id"), designer.id)

    def test_customer_form_auto_assigns_single_designer_for_shop_session(self):
        admin = AdminAccount.objects.create(
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
        designer = Designer.objects.create(
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
                "age": "31",
                "phone": "010-2020-3030",
            },
        )

        self.assertEqual(response.status_code, 302)
        client = Client.objects.get(phone="01020203030")
        self.assertEqual(client.shop_id, admin.id)
        self.assertEqual(client.designer_id, designer.id)
        self.assertEqual(client.assignment_source, "auto_single_designer")

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
        self.assertIsNotNone(self.client.session.get("admin_id"))

    def test_admin_register_api_returns_field_errors_for_duplicate_phone(self):
        AdminAccount.objects.create(
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
        client = Client.objects.create(name="Legacy Client", phone="01033334444")
        survey = Survey.objects.create(
            client=client,
            target_length="short",
            target_vibe="soft",
            scalp_type="normal",
            hair_colour="black",
            budget_range="10-15",
            preference_vector=[0.3] * 20,
        )
        capture = CaptureRecord.objects.create(
            client=client,
            status="DONE",
            face_count=1,
            processed_path="captures/client.jpg",
            privacy_snapshot={"storage_policy": "asset_store"},
        )
        analysis = FaceAnalysis.objects.create(
            client=client,
            face_shape="Oval",
            golden_ratio_score=0.91,
            image_url="captures/client.jpg",
            landmark_snapshot={"version": "coarse-v1"},
        )
        persist_generated_batch(client=client, capture_record=capture, survey=survey, analysis=analysis)

        response = self.client.get(f"/api/v1/analysis/recommendations/?customer_id={client.id}")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        self.assertGreaterEqual(len(response.json()), 1)
        self.assertIn("reference_images", response.json()[0])

    def test_capture_upload_accepts_customer_id_alias(self):
        client = Client.objects.create(name="Capture Alias", phone="01077776666")
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
        client = Client.objects.create(name="Capture Status", phone="01010101010")
        record = CaptureRecord.objects.create(
            client=client,
            status="DONE",
            face_count=1,
            original_path="captures/original.jpg",
            processed_path="captures/processed.jpg",
            deidentified_path="captures/deidentified.jpg",
            privacy_snapshot={"storage_policy": "asset_store"},
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
        client = Client.objects.create(name="Survey Alias", phone="01012121212")

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
        survey = Survey.objects.get(client=client)
        self.assertEqual(survey.target_length, "short")
        self.assertEqual(survey.target_vibe, "soft")

    def test_survey_endpoint_maps_male_q1_to_q6_answers(self):
        client = Client.objects.create(name="Male Survey", phone="01012120001", gender="male")

        response = self.client.post(
            "/api/v1/survey/",
            {
                "customer": client.id,
                "q1": "아주 짧고 깔끔하게",
                "q2": "확실한 투블럭",
                "q3": "올리는 스타일",
                "q4": "가르마 스타일 선호",
                "q5": "자연스러운 볼륨 정도",
                "q6": "트렌디한",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        survey = Survey.objects.get(client=client)
        self.assertEqual(survey.target_length, "short")
        self.assertEqual(survey.target_vibe, "chic")
        self.assertEqual(survey.scalp_type, "waved")
        self.assertEqual(survey.hair_colour, "unknown")
        self.assertEqual(survey.budget_range, "unknown")
        self.assertTrue(any(survey.preference_vector))

    def test_survey_endpoint_maps_female_q1_to_q6_answers(self):
        client = Client.objects.create(name="Female Survey", phone="01012120002", gender="female")

        response = self.client.post(
            "/api/v1/survey/",
            {
                "customer": client.id,
                "q1": "길게",
                "q2": "레이어감 있는 스타일",
                "q3": "시스루·가벼운 앞머리",
                "q4": "끝선 위주 자연스러운 컬",
                "q5": "고급스러운",
                "q6": "확실히 이미지 변신하고 싶음",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        survey = Survey.objects.get(client=client)
        self.assertEqual(survey.target_length, "long")
        self.assertEqual(survey.target_vibe, "elegant")
        self.assertEqual(survey.scalp_type, "waved")
        self.assertEqual(survey.hair_colour, "unknown")
        self.assertEqual(survey.budget_range, "unknown")
        self.assertTrue(any(survey.preference_vector))

    def test_legacy_admin_customer_and_report_endpoints_work_with_session(self):
        admin = AdminAccount.objects.create(
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
        client = Client.objects.create(name="Admin View Client", phone="01011112222")
        Survey.objects.create(
            client=client,
            target_length="medium",
            target_vibe="chic",
            scalp_type="normal",
            hair_colour="brown",
            budget_range="10-15",
            preference_vector=[0.5] * 20,
        )
        CaptureRecord.objects.create(
            client=client,
            status="DONE",
            face_count=1,
            processed_path="captures/admin-view.jpg",
            privacy_snapshot={"storage_policy": "asset_store"},
        )
        FaceAnalysis.objects.create(
            client=client,
            face_shape="Oval",
            golden_ratio_score=0.88,
            image_url="captures/admin-view.jpg",
            landmark_snapshot={"version": "coarse-v1"},
        )
        StyleSelection.objects.create(
            client=client,
            style_id=201,
            source="current_recommendations",
            match_score=0.82,
            is_sent_to_admin=True,
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

    def test_legacy_admin_customer_and_report_endpoints_scope_to_designer_session(self):
        admin = AdminAccount.objects.create(
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
        designer = Designer.objects.create(
            shop=admin,
            name="Scoped Designer",
            pin_hash=make_password("4567"),
        )
        own_client = Client.objects.create(name="Own Client", phone="01055550001", shop=admin, designer=designer)
        other_client = Client.objects.create(name="Other Client", phone="01055550002", shop=admin)
        StyleSelection.objects.create(client=own_client, style_id=301, source="current_recommendations", match_score=0.91, is_sent_to_admin=True)
        StyleSelection.objects.create(client=other_client, style_id=302, source="current_recommendations", match_score=0.81, is_sent_to_admin=True)

        self._set_designer_session(designer)

        list_response = self.client.get("/api/v1/customers/")
        report_response = self.client.get("/api/v1/analysis/report/")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)
        self.assertEqual(list_response.json()[0]["id"], own_client.id)
        self.assertEqual(report_response.status_code, 200)
