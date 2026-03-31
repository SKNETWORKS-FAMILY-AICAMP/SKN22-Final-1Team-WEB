from django.core.management import call_command
from django.test import TestCase, override_settings

from app.models_django import (
    AdminAccount,
    CaptureRecord,
    Client,
    ConsultationRequest,
    Designer,
    FaceAnalysis,
    FormerRecommendation,
    StyleSelection,
    Survey,
)


@override_settings(SUPABASE_USE_REMOTE_STORAGE=False)
class SeedTestAccountsCommandTests(TestCase):
    def test_seed_command_populates_partner_and_downstream_records(self):
        call_command("seed_test_accounts")

        shop = AdminAccount.objects.get(phone="01080001000")
        self.assertEqual(shop.business_number, "1012345672")

        designers = Designer.objects.filter(shop=shop, is_active=True).order_by("name")
        self.assertEqual(designers.count(), 2)

        clients = Client.objects.filter(shop=shop).order_by("phone")
        self.assertEqual(clients.count(), 4)
        self.assertEqual(Survey.objects.filter(client__shop=shop).count(), 4)

        full_flow_client = Client.objects.get(phone="01090001001")
        current_flow_client = Client.objects.get(phone="01090001003")
        pending_client = Client.objects.get(phone="01090001004")

        self.assertTrue(
            CaptureRecord.objects.filter(client=full_flow_client, status="DONE").exists()
        )
        self.assertTrue(FaceAnalysis.objects.filter(client=full_flow_client).exists())
        self.assertTrue(
            FormerRecommendation.objects.filter(client=full_flow_client, source="generated").exists()
        )
        self.assertTrue(
            FormerRecommendation.objects.filter(client=full_flow_client, is_chosen=True).exists()
        )
        self.assertTrue(
            StyleSelection.objects.filter(client=full_flow_client, source="seed_test_accounts").exists()
        )
        self.assertTrue(
            ConsultationRequest.objects.filter(client=full_flow_client, is_active=True).exists()
        )

        self.assertTrue(
            FormerRecommendation.objects.filter(client=current_flow_client, source="generated").exists()
        )
        self.assertFalse(
            FormerRecommendation.objects.filter(client=current_flow_client, is_chosen=True).exists()
        )
        self.assertFalse(
            StyleSelection.objects.filter(client=current_flow_client, source="seed_test_accounts").exists()
        )

        self.assertFalse(
            CaptureRecord.objects.filter(client=pending_client).exists()
        )
        self.assertIsNone(pending_client.designer_id)

    def test_verify_seed_integrity_passes_after_seed(self):
        call_command("seed_test_accounts")
        call_command("verify_seed_integrity", strict=True)
