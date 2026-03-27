import io
import shutil
import tempfile

from django.contrib.auth.hashers import make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from app.api.v1.services_django import persist_generated_batch
from app.models_django import AdminAccount, CaptureRecord, Client, FaceAnalysis, StyleSelection, Survey


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
        self.assertIn("status", response.json())

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
