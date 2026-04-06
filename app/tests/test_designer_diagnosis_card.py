import json

from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings

from app.models_django import ClientProfileNote, DesignerDiagnosisCard
from app.models_model_team import LegacyClient
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
        session[OWNER_DASHBOARD_ALLOWED_SESSION_KEY] = False
        session.save()
        return designer

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
