from django.core.management import call_command
from django.test import TestCase, override_settings
from io import StringIO

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
from app.services.model_team_bridge import get_admin_by_phone


@override_settings(SUPABASE_USE_REMOTE_STORAGE=False)
class SeedTestAccountsCommandTests(TestCase):
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
