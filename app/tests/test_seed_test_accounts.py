from django.core.management import call_command
from django.test import TestCase, override_settings
from io import StringIO

from app.services.model_team_bridge import get_admin_by_phone, get_legacy_admin_id
from app.session_state import (
    ADMIN_ID_SESSION_KEY,
    ADMIN_LEGACY_ID_SESSION_KEY,
    ADMIN_NAME_SESSION_KEY,
    ADMIN_STORE_NAME_SESSION_KEY,
    OWNER_DASHBOARD_ALLOWED_SESSION_KEY,
)

from app.models_django import (
    ConsultationRequest,
)
from app.models_model_team import (
    LegacyClient,
    LegacyClientAnalysis,
    LegacyClientResult,
    LegacyClientResultDetail,
    LegacyClientSurvey,
    LegacyDesigner,
    LegacyShop,
)


@override_settings(SUPABASE_USE_REMOTE_STORAGE=False)
class SeedTestAccountsCommandTests(TestCase):
    def _login_shop_session(self, shop):
        session = self.client.session
        session[ADMIN_ID_SESSION_KEY] = shop.id
        session[ADMIN_LEGACY_ID_SESSION_KEY] = get_legacy_admin_id(admin=shop)
        session[ADMIN_STORE_NAME_SESSION_KEY] = shop.store_name
        session[ADMIN_NAME_SESSION_KEY] = shop.name
        session[OWNER_DASHBOARD_ALLOWED_SESSION_KEY] = True
        session.save()

    def test_seed_command_populates_partner_and_downstream_records(self):
        call_command("seed_test_accounts")

        shop = get_admin_by_phone(phone="01080001000")
        self.assertIsNotNone(shop)
        self.assertEqual(shop.business_number, "1012345672")

        designers = LegacyDesigner.objects.filter(backend_shop_ref_id=shop.id, is_active=True).order_by("name")
        self.assertEqual(designers.count(), 2)

        clients = LegacyClient.objects.filter(backend_shop_ref_id=shop.id).order_by("phone")
        self.assertEqual(clients.count(), 4)
        self.assertEqual(
            LegacyClientSurvey.objects.filter(
                backend_client_ref_id__in=clients.values_list("backend_client_id", flat=True)
            ).count(),
            4,
        )

        full_flow_client = LegacyClient.objects.get(phone="01090001001")
        current_flow_client = LegacyClient.objects.get(phone="01090001003")
        pending_client = LegacyClient.objects.get(phone="01090001004")

        self.assertTrue(
            LegacyClientAnalysis.objects.filter(backend_client_ref_id=full_flow_client.backend_client_id).exists()
        )
        self.assertTrue(
            LegacyClientResultDetail.objects.filter(
                backend_client_ref_id=full_flow_client.backend_client_id,
                source="generated",
            ).exists()
        )
        self.assertTrue(
            LegacyClientResultDetail.objects.filter(
                backend_client_ref_id=full_flow_client.backend_client_id,
                is_chosen=True,
            ).exists()
        )
        self.assertTrue(
            LegacyClientResult.objects.filter(
                backend_client_ref_id=full_flow_client.backend_client_id,
                source="seed_test_accounts",
                is_confirmed=True,
            ).exists()
        )
        self.assertTrue(
            ConsultationRequest.objects.filter(
                backend_client_ref_id=full_flow_client.backend_client_id,
                is_active=True,
            ).exists()
        )

        self.assertTrue(
            LegacyClientResultDetail.objects.filter(
                backend_client_ref_id=current_flow_client.backend_client_id,
                source="generated",
            ).exists()
        )
        self.assertFalse(
            LegacyClientResultDetail.objects.filter(
                backend_client_ref_id=current_flow_client.backend_client_id,
                is_chosen=True,
            ).exists()
        )
        self.assertFalse(
            LegacyClientResult.objects.filter(
                backend_client_ref_id=current_flow_client.backend_client_id,
                source="seed_test_accounts",
                is_confirmed=True,
            ).exists()
        )

        self.assertFalse(
            LegacyClientAnalysis.objects.filter(backend_client_ref_id=pending_client.backend_client_id).exists()
        )
        self.assertIsNone(pending_client.backend_designer_ref_id)

    def test_legacy_customer_list_exposes_visit_summary_fields(self):
        call_command("seed_test_accounts")
        shop = get_admin_by_phone(phone="01080001000")
        self._login_shop_session(shop)

        response = self.client.get("/api/v1/customers/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        by_phone = {item["phone"]: item for item in payload}

        full_flow_client = LegacyClient.objects.get(phone="01090001001")
        current_flow_client = LegacyClient.objects.get(phone="01090001003")
        pending_client = LegacyClient.objects.get(phone="01090001004")

        full_flow_item = by_phone[full_flow_client.phone]
        current_flow_item = by_phone[current_flow_client.phone]
        pending_item = by_phone[pending_client.phone]

        self.assertIn("last_visit_date", full_flow_item)
        self.assertIn("visit_count", full_flow_item)
        self.assertEqual(
            full_flow_item["visit_count"],
            LegacyClientResult.objects.filter(backend_client_ref_id=full_flow_client.backend_client_id).count(),
        )
        self.assertEqual(
            current_flow_item["visit_count"],
            LegacyClientResult.objects.filter(backend_client_ref_id=current_flow_client.backend_client_id).count(),
        )
        self.assertEqual(pending_item["visit_count"], 0)
        self.assertIsNotNone(full_flow_item["last_visit_date"])
        self.assertIsNotNone(current_flow_item["last_visit_date"])
        self.assertIsNone(pending_item["last_visit_date"])

    def test_legacy_customer_detail_exposes_reanalysis_messages(self):
        call_command("seed_test_accounts")
        shop = get_admin_by_phone(phone="01080001000")
        self._login_shop_session(shop)
        client_record = LegacyClient.objects.get(phone="01090001001")

        response = self.client.get(f"/api/v1/customers/{client_record.backend_client_id}/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        reanalysis = payload["reanalysis"]

        self.assertEqual(reanalysis["state"], "consultation_locked")
        self.assertEqual(reanalysis["reason_code"], "consultation_started")
        self.assertTrue(reanalysis["user_message"])
        self.assertEqual(reanalysis["keep_preference_block_reason"], "consultation_started")
        self.assertEqual(reanalysis["choose_again_block_reason"], "consultation_started")
        self.assertEqual(reanalysis["retry_block_reason"], "consultation_started")
        self.assertEqual(reanalysis["debug"]["legacy_reason_fields"]["keep_preference_block_reason"], "consultation_started")
        self.assertEqual(reanalysis["debug"]["legacy_reason_fields"]["choose_again_block_reason"], "consultation_started")
        self.assertEqual(reanalysis["debug"]["legacy_reason_fields"]["retry_block_reason"], "consultation_started")
        self.assertEqual(reanalysis["debug"]["legacy_reason_fields"]["consultation_locked"], True)
        self.assertNotIn("message", reanalysis)
        self.assertNotIn("keep_preference_block_message", reanalysis)
        self.assertNotIn("choose_again_block_message", reanalysis)
        self.assertNotIn("retry_block_message", reanalysis)

    def test_verify_seed_integrity_passes_after_seed(self):
        call_command("seed_test_accounts")
        call_command("verify_seed_integrity", strict=True)

    def test_audit_model_team_cutover_passes_after_seed(self):
        call_command("seed_test_accounts")
        stdout = StringIO()
        call_command("audit_model_team_cutover", strict=True, stdout=stdout)
        output = stdout.getvalue()
        self.assertIn("legacy strict integrity: passed", output)
        self.assertIn("canonical drop candidates:", output)
        self.assertIn("backend-only exceptions:", output)
