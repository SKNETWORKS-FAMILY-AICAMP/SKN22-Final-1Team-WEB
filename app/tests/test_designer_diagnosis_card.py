import io
import json
from unittest.mock import patch

from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings

from app.models_django import ClientProfileNote, DesignerDiagnosisCard
from PIL import Image

from app.models_model_team import LegacyClient, LegacyClientAnalysis
from app.services.model_team_bridge import (
    get_admin_by_phone,
    get_legacy_active_consultation_items,
    get_legacy_admin_id,
    get_legacy_designer_id,
    get_designers_for_admin,
)
from app.session_state import (
    ADMIN_ID_SESSION_KEY,
    ADMIN_LEGACY_ID_SESSION_KEY,
    ADMIN_NAME_SESSION_KEY,
    ADMIN_STORE_NAME_SESSION_KEY,
    DESIGNER_DASHBOARD_ALLOWED_SESSION_KEY,
    DESIGNER_ID_SESSION_KEY,
    DESIGNER_LEGACY_ID_SESSION_KEY,
    DESIGNER_NAME_SESSION_KEY,
    OWNER_DASHBOARD_ALLOWED_SESSION_KEY,
)


@override_settings(
    SUPABASE_USE_REMOTE_STORAGE=False,
    DEBUG=True,
    STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
)
class DesignerDiagnosisCardFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_test_accounts")
        cls.shop = get_admin_by_phone(phone="01080001000")
        cls.client_record = LegacyClient.objects.get(phone="01090001003")
        cls.client_id = cls.client_record.backend_client_id
        active_consultations = get_legacy_active_consultation_items(admin=cls.shop) or []
        if not active_consultations:
            raise AssertionError("seed_test_accounts must provide at least one active consultation for checklist 4 tests.")
        cls.active_consultation = active_consultations[0]
        cls.consultation_client_id = cls.active_consultation["client_id"]
        cls.consultation_id = cls.active_consultation["consultation_id"]

    def _login_shop_session(self):
        session = self.client.session
        session[ADMIN_ID_SESSION_KEY] = self.shop.id
        session[ADMIN_LEGACY_ID_SESSION_KEY] = get_legacy_admin_id(admin=self.shop)
        session[ADMIN_STORE_NAME_SESSION_KEY] = self.shop.store_name
        session[ADMIN_NAME_SESSION_KEY] = self.shop.name
        session[OWNER_DASHBOARD_ALLOWED_SESSION_KEY] = True
        session.save()

    def _login_designer_session(self):
        self._login_shop_session()
        designer = get_designers_for_admin(admin=self.shop)[0]
        session = self.client.session
        session[DESIGNER_ID_SESSION_KEY] = designer.id
        session[DESIGNER_LEGACY_ID_SESSION_KEY] = get_legacy_designer_id(designer=designer)
        session[DESIGNER_NAME_SESSION_KEY] = designer.name
        session[DESIGNER_DASHBOARD_ALLOWED_SESSION_KEY] = True
        session[OWNER_DASHBOARD_ALLOWED_SESSION_KEY] = False
        session.save()
        return designer

    def _build_test_upload_file(self, *, size=(400, 400), color=(128, 128, 128), name="capture.jpg"):
        buffer = io.BytesIO()
        Image.new("RGB", size, color).save(buffer, format="JPEG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")

    def test_legacy_customer_detail_exposes_session_status_and_empty_payloads(self):
        self._login_shop_session()

        response = self.client.get(f"/api/v1/customers/{self.client_id}/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        diagnosis = payload["designer_diagnosis"]
        customer_note = payload["customer_note"]
        session_status = payload["session_status"]

        self.assertEqual(diagnosis["hair_texture"], "")
        self.assertEqual(diagnosis["damage_level"], "")
        self.assertEqual(diagnosis["special_notes"], [])
        self.assertEqual(diagnosis["special_memo"], "")
        self.assertFalse(diagnosis["has_content"])
        self.assertTrue(diagnosis["storage_ready"])

        self.assertEqual(customer_note["content"], "")
        self.assertFalse(customer_note["has_content"])
        self.assertTrue(customer_note["storage_ready"])

        self.assertFalse(session_status["is_active"])
        self.assertFalse(session_status["can_write_designer_diagnosis"])
        self.assertEqual(session_status["customer_note_scope"], "client")

    def test_legacy_customer_detail_defers_heavy_history_payload_by_default(self):
        self._login_shop_session()

        with patch(
            "app.api.v1.admin_services.get_legacy_capture_history",
            side_effect=AssertionError("capture history should not be fetched on initial detail render"),
        ), patch(
            "app.api.v1.admin_services.get_legacy_analysis_history",
            side_effect=AssertionError("analysis history should not be fetched on initial detail render"),
        ), patch(
            "app.api.v1.admin_services.get_legacy_confirmed_selection_items",
            side_effect=AssertionError("selection history should not be fetched on initial detail render"),
        ):
            response = self.client.get(f"/api/v1/customers/{self.client_id}/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["history"]["deferred"])
        self.assertIn("history_url", payload["history"])
        self.assertLessEqual(len(payload["face_analyses"]), 1)
        self.assertLessEqual(len(payload["captures"]), 1)
        self.assertEqual(payload["notes"], [])

    def test_legacy_customer_history_endpoint_returns_full_history_payload(self):
        self._login_shop_session()

        response = self.client.get(f"/api/v1/customers/{self.client_id}/history/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["history"]["deferred"])
        self.assertIn("timings_ms", payload["history"])
        self.assertIn("counts", payload["history"])
        self.assertIn("capture_history", payload)
        self.assertIn("analysis_history", payload)
        self.assertIn("style_selection_history", payload)
        self.assertIn("chosen_recommendation_history", payload)
        self.assertIn("notes", payload)

    def test_legacy_customer_detail_can_include_history_when_requested(self):
        self._login_shop_session()

        response = self.client.get(
            f"/api/v1/customers/{self.client_id}/?include_history=1&history_limit=5"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["history"]["deferred"])
        self.assertLessEqual(len(payload["face_analyses"]), 5)

    def test_dashboard_and_customer_detail_session_status_match_for_active_client(self):
        self._login_shop_session()

        list_response = self.client.get("/api/v1/customers/")
        self.assertEqual(list_response.status_code, 200)
        list_payload = list_response.json()
        list_items = list_payload["items"] if isinstance(list_payload, dict) else list_payload
        active_row = next(
            item for item in list_items
            if item["client_id"] == self.consultation_client_id
        )

        detail_response = self.client.get(f"/api/v1/customers/{self.consultation_client_id}/")
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = detail_response.json()

        self.assertTrue(active_row["session_active"])
        self.assertTrue(active_row["has_active_consultation"])
        self.assertTrue(active_row["can_write_designer_diagnosis"])
        self.assertTrue(detail_payload["session_status"]["is_active"])
        self.assertTrue(detail_payload["session_status"]["can_write_designer_diagnosis"])

    def test_designer_dashboard_renders_chatbot_component(self):
        self._login_designer_session()

        response = self.client.get("/partner/staff/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-chatbot-placement="designer-dashboard"')
        self.assertContains(response, 'id="mirraiChatbot"', count=1)
        self.assertContains(response, 'shared/js/chatbot.js')

    def test_analysis_designer_selection_keeps_designer_session_but_requires_pin_for_staff_dashboard(self):
        self._login_shop_session()
        designer = get_designers_for_admin(admin=self.shop)[0]

        response = self.client.post("/partner/select-designer/", {"designer_id": str(designer.id)})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        session = self.client.session
        self.assertEqual(str(session[DESIGNER_ID_SESSION_KEY]), str(designer.id))
        self.assertFalse(session.get(DESIGNER_DASHBOARD_ALLOWED_SESSION_KEY, False))

        staff_response = self.client.get("/partner/staff/")
        self.assertEqual(staff_response.status_code, 302)
        self.assertIn(f"designer_id={designer.id}", staff_response["Location"])
        self.assertIn("next=/partner/staff/", staff_response["Location"])

    def test_designer_detail_page_does_not_require_reselect_after_pin_login(self):
        self._login_designer_session()

        response = self.client.get(f"/partner/customer-detail/{self.client_id}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="customerDetailChatbotTemplate"')

    def test_shop_dashboard_does_not_render_designer_chatbot_component(self):
        self._login_shop_session()

        response = self.client.get("/partner/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-chatbot-placement="designer-dashboard"')

    def test_customer_detail_renders_separate_chatbot_extension(self):
        self._login_shop_session()

        response = self.client.get(f"/partner/customer-detail/{self.client_id}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="customerDetailChatbotTemplate"')
        self.assertContains(response, 'data-chatbot-placement="customer-detail-extension"')
        self.assertContains(response, 'shared/js/chatbot.js')

    def test_designer_diagnosis_card_rejects_save_without_active_session(self):
        self._login_shop_session()

        response = self.client.post(
            f"/api/v1/customers/{self.client_id}/diagnosis-card/",
            data=json.dumps(
                {
                    "hair_texture": "fine",
                    "damage_level": "level2",
                    "special_notes": ["bleach_history"],
                    "special_memo": "세션 없는 고객은 저장이 막혀야 합니다.",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("세션이 활성화된 고객만 진단 카드를 작성할 수 있습니다.", payload["detail"])
        self.assertFalse(DesignerDiagnosisCard.objects.filter(client_ref_id=self.client_id).exists())

    def test_designer_diagnosis_card_save_and_detail_roundtrip_for_active_session(self):
        self._login_shop_session()

        payload = {
            "hair_texture": "fine",
            "damage_level": "level2",
            "special_notes": ["bleach_history", "self_coloring"],
            "special_memo": "Ends are dry, keep the heat lower.",
        }
        response = self.client.post(
            f"/api/v1/customers/{self.consultation_client_id}/diagnosis-card/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        saved_payload = response.json()["designer_diagnosis"]
        self.assertEqual(saved_payload["hair_texture"], "fine")
        self.assertEqual(saved_payload["damage_level"], "level2")
        self.assertEqual(saved_payload["special_notes"], ["bleach_history", "self_coloring"])
        self.assertEqual(saved_payload["special_memo"], "Ends are dry, keep the heat lower.")
        self.assertTrue(saved_payload["has_content"])
        self.assertEqual(saved_payload["updated_by"]["role"], "admin")

        card = DesignerDiagnosisCard.objects.get(client_ref_id=self.consultation_client_id)
        self.assertEqual(card.hair_texture, "fine")
        self.assertEqual(card.damage_level, "level2")
        self.assertEqual(card.special_notes, ["bleach_history", "self_coloring"])

        detail_response = self.client.get(f"/api/v1/customers/{self.consultation_client_id}/")
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = detail_response.json()
        detail_diagnosis = detail_payload["designer_diagnosis"]
        self.assertEqual(detail_diagnosis["hair_texture"], "fine")
        self.assertEqual(detail_diagnosis["damage_level"], "level2")
        self.assertEqual(detail_diagnosis["special_notes"], ["bleach_history", "self_coloring"])
        self.assertEqual(detail_diagnosis["special_memo"], "Ends are dry, keep the heat lower.")
        self.assertTrue(detail_payload["session_status"]["is_active"])
        self.assertTrue(detail_payload["session_status"]["can_write_designer_diagnosis"])

    def test_blank_payload_clears_saved_designer_diagnosis_card_for_active_session(self):
        self._login_shop_session()

        self.client.post(
            f"/api/v1/customers/{self.consultation_client_id}/diagnosis-card/",
            data=json.dumps(
                {
                    "hair_texture": "coarse",
                    "damage_level": "level4",
                    "special_notes": ["head_shape_density"],
                    "special_memo": "Temporary diagnosis.",
                }
            ),
            content_type="application/json",
        )

        response = self.client.post(
            f"/api/v1/customers/{self.consultation_client_id}/diagnosis-card/",
            data=json.dumps(
                {
                    "hair_texture": "",
                    "damage_level": "",
                    "special_notes": [],
                    "special_memo": "",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        cleared_payload = response.json()["designer_diagnosis"]
        self.assertFalse(cleared_payload["has_content"])
        self.assertEqual(cleared_payload["special_notes"], [])
        self.assertFalse(DesignerDiagnosisCard.objects.filter(client_ref_id=self.consultation_client_id).exists())

    def test_customer_note_save_returns_korean_success_message_without_consultation(self):
        self._login_shop_session()

        response = self.client.post(
            f"/api/v1/customers/{self.client_id}/customer-note/",
            data=json.dumps({"content": "고객은 볼륨을 원하지만 끝선 손상 케어를 우선 원합니다."}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["message"], "저장 완료되었습니다.")
        self.assertEqual(payload["customer_note"]["content"], "고객은 볼륨을 원하지만 끝선 손상 케어를 우선 원합니다.")
        self.assertTrue(payload["customer_note"]["has_content"])

        note = ClientProfileNote.objects.get(client_ref_id=self.client_id)
        self.assertEqual(note.content, "고객은 볼륨을 원하지만 끝선 손상 케어를 우선 원합니다.")

    def test_customer_detail_includes_saved_customer_note_and_remains_json(self):
        self._login_shop_session()

        save_response = self.client.post(
            f"/api/v1/customers/{self.client_id}/customer-note/",
            data=json.dumps({"content": "재방문 전 고객 메모를 저장했습니다."}),
            content_type="application/json",
        )
        self.assertEqual(save_response.status_code, 200)

        detail_response = self.client.get(f"/api/v1/customers/{self.client_id}/")
        self.assertEqual(detail_response.status_code, 200)

        payload = detail_response.json()
        customer_note = payload["customer_note"]
        self.assertEqual(customer_note["content"], "재방문 전 고객 메모를 저장했습니다.")
        self.assertTrue(customer_note["has_content"])
        self.assertFalse(payload["session_status"]["is_active"])
        self.assertFalse(payload["session_status"]["can_write_designer_diagnosis"])

    def test_customer_note_blank_payload_clears_saved_note(self):
        self._login_shop_session()

        self.client.post(
            f"/api/v1/customers/{self.client_id}/customer-note/",
            data=json.dumps({"content": "지워질 고객 메모"}),
            content_type="application/json",
        )

        response = self.client.post(
            f"/api/v1/customers/{self.client_id}/customer-note/",
            data=json.dumps({"content": ""}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["message"], "저장 완료되었습니다.")
        self.assertEqual(payload["customer_note"]["content"], "")
        self.assertFalse(payload["customer_note"]["has_content"])
        self.assertFalse(ClientProfileNote.objects.filter(client_ref_id=self.client_id).exists())

    def test_consultation_note_save_returns_korean_success_message(self):
        self._login_shop_session()

        response = self.client.post(
            f"/api/v1/customers/{self.consultation_client_id}/consultation-note/",
            data=json.dumps(
                {
                    "consultation_id": self.consultation_id,
                    "content": "고객은 볼륨은 원하지만 끝선 손상 케어를 우선 원합니다.",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["message"], "저장 완료되었습니다.")
        self.assertEqual(payload["consultation_id"], self.consultation_id)
        self.assertIsInstance(payload["note_id"], int)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT content FROM client_session_notes WHERE id = %s",
                [payload["note_id"]],
            )
            row = cursor.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "고객은 볼륨은 원하지만 끝선 손상 케어를 우선 원합니다.")

    def test_capture_upload_failure_stores_diagnostics_and_reason_code(self):
        self._login_shop_session()

        response = self.client.post(
            "/api/v1/capture/upload/",
            data={
                "customer_id": str(self.client_id),
                "file": self._build_test_upload_file(),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "needs_retake")
        self.assertEqual(payload["reason_code"], "no_face_detected")

        diagnostics = payload["privacy_snapshot"]["capture_validation"]["diagnostics"]
        thresholds = payload["privacy_snapshot"]["capture_validation"]["thresholds"]
        self.assertIn("brightness", diagnostics)
        self.assertIn("sharpness", diagnostics)
        self.assertIn("min_brightness", thresholds)
        self.assertIn("min_sharpness", thresholds)

        record = LegacyClientAnalysis.objects.get(analysis_id=payload["record_id"])
        validation_snapshot = record.privacy_snapshot["capture_validation"]
        self.assertEqual(validation_snapshot["reason_code"], "no_face_detected")
        self.assertFalse(validation_snapshot["front_capture_context_present"])

    def test_capture_upload_failure_marks_backend_failed_after_front_ready_when_context_sent(self):
        self._login_shop_session()

        response = self.client.post(
            "/api/v1/capture/upload/",
            data={
                "customer_id": str(self.client_id),
                "front_capture_context": json.dumps(
                    {
                        "all_valid": True,
                        "message_key": "ready_to_capture",
                        "checklist_summary": "5/5 pass",
                    }
                ),
                "file": self._build_test_upload_file(name="capture-front-context.jpg"),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        validation_snapshot = payload["privacy_snapshot"]["capture_validation"]
        self.assertTrue(validation_snapshot["front_capture_context_present"])
        self.assertTrue(validation_snapshot["front_all_valid"])
        self.assertTrue(validation_snapshot["backend_failed_after_front_ready"])
        self.assertEqual(validation_snapshot["front_message_key"], "ready_to_capture")

    def test_capture_failure_analysis_command_summarizes_reason_codes(self):
        self._login_shop_session()

        self.client.post(
            "/api/v1/capture/upload/",
            data={
                "customer_id": str(self.client_id),
                "front_capture_context": json.dumps({"all_valid": True, "message_key": "ready_to_capture"}),
                "file": self._build_test_upload_file(name="capture-summary.jpg"),
            },
        )

        stdout = io.StringIO()
        call_command("analyze_capture_upload_failures", "--limit", "20", stdout=stdout)
        output = stdout.getvalue()

        self.assertIn("Capture upload pattern summary", output)
        self.assertIn("Reason counts:", output)
        self.assertIn("no_face_detected", output)
        self.assertIn("backend_failed_after_front_ready", output)

    def test_capture_validation_accepts_equalized_single_face_fallback(self):
        from app.services import capture_validation

        image_file = self._build_test_upload_file()
        image_bytes = image_file.read()

        with patch.object(capture_validation, "MIN_SHARPNESS", 0), patch(
            "app.services.capture_validation._detect_faces",
            side_effect=[[], [(12, 18, 180, 190)]],
        ):
            result = capture_validation.validate_capture_image(processed_bytes=image_bytes)

        self.assertTrue(result["is_valid"])
        self.assertEqual(result["face_count"], 1)
        self.assertEqual(result["reason_code"], "ok")

    def test_capture_validation_accepts_stricter_single_face_resolution_for_multiple_faces(self):
        from app.services import capture_validation

        image_file = self._build_test_upload_file()
        image_bytes = image_file.read()

        with patch.object(capture_validation, "MIN_SHARPNESS", 0), patch(
            "app.services.capture_validation._detect_faces",
            side_effect=[[(10, 10, 180, 180), (28, 24, 170, 170)], [(14, 12, 182, 184)]],
        ):
            result = capture_validation.validate_capture_image(processed_bytes=image_bytes)

        self.assertTrue(result["is_valid"])
        self.assertEqual(result["face_count"], 1)
        self.assertEqual(result["reason_code"], "ok")

