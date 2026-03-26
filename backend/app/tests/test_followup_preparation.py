import os
from unittest import mock

from django.contrib.auth.hashers import make_password
from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from app.api.v1.admin_auth import build_admin_refresh_token, build_client_refresh_token, get_admin_auth_policy_snapshot
from app.api.v1.response_helpers import get_error_contract_snapshot
from app.api.v1.services_django import persist_generated_batch
from app.models_django import AdminAccount, CaptureRecord, Client, FaceAnalysis, Survey


class ContractPreparationSnapshotTests(SimpleTestCase):
    def test_error_contract_snapshot_reports_current_detail_mode(self):
        payload = get_error_contract_snapshot()

        self.assertEqual(payload["mode"], "drf_detail")
        self.assertEqual(payload["fields"], ["detail"])
        self.assertFalse(payload["envelope_supported"])

    def test_admin_auth_policy_snapshot_reports_refresh_support(self):
        payload = get_admin_auth_policy_snapshot()

        self.assertEqual(payload["token_type"], "bearer")
        self.assertTrue(payload["refresh_token_supported"])
        self.assertGreater(payload["token_max_age_seconds"], 0)
        self.assertGreater(payload["refresh_token_max_age_seconds"], payload["token_max_age_seconds"])


class RegenerateSimulationEndpointTests(APITestCase):
    @mock.patch.dict(os.environ, {"MIRRAI_AI_PROVIDER": "local"}, clear=False)
    def test_regenerate_simulation_endpoint_returns_card_for_vector_only_row(self):
        client = Client.objects.create(name="Regen Tester", phone="01012121212", gender="F")
        survey = Survey.objects.create(
            client=client,
            target_length="medium",
            target_vibe="soft",
            scalp_type="normal",
            hair_colour="brown",
            budget_range="10-15",
            preference_vector=[0.6] * 20,
        )
        capture = CaptureRecord.objects.create(
            client=client,
            status="DONE",
            face_count=1,
            privacy_snapshot={"storage_policy": "vector_only"},
        )
        analysis = FaceAnalysis.objects.create(
            client=client,
            face_shape="Oval",
            golden_ratio_score=0.89,
            image_url=None,
            landmark_snapshot={"version": "coarse-v1"},
        )
        _, rows = persist_generated_batch(
            client=client,
            capture_record=capture,
            survey=survey,
            analysis=analysis,
        )

        response = self.client.post(
            "/api/v1/analysis/regenerate-simulation/",
            {"recommendation_id": rows[0].id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        self.assertEqual(response.data["recommendation_id"], rows[0].id)
        self.assertEqual(response.data["image_policy"], "vector_only")
        self.assertEqual(response.data["card"]["style_id"], rows[0].style_id_snapshot)
        self.assertFalse(response.data["card"]["can_regenerate_simulation"])
        self.assertEqual(response.data["card"]["regeneration_remaining_count"], 0)
        self.assertIn("regenerated", response.data["card"]["reasoning_snapshot"])

        second_response = self.client.post(
            "/api/v1/analysis/regenerate-simulation/",
            {"recommendation_id": rows[0].id},
            format="json",
        )
        self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch.dict(os.environ, {"MIRRAI_AI_PROVIDER": "local"}, clear=False)
    def test_regenerate_simulation_endpoint_accepts_snapshot_and_style_id(self):
        client = Client.objects.create(name="Snapshot Tester", phone="01034343434", gender="F")
        survey = Survey.objects.create(
            client=client,
            target_length="short",
            target_vibe="chic",
            scalp_type="normal",
            hair_colour="black",
            budget_range="10-15",
            preference_vector=[0.4] * 20,
        )
        capture = CaptureRecord.objects.create(
            client=client,
            status="DONE",
            face_count=1,
            privacy_snapshot={"storage_policy": "vector_only"},
        )
        analysis = FaceAnalysis.objects.create(
            client=client,
            face_shape="Oval",
            golden_ratio_score=0.9,
            image_url=None,
            landmark_snapshot={"version": "coarse-v1"},
        )
        _, rows = persist_generated_batch(
            client=client,
            capture_record=capture,
            survey=survey,
            analysis=analysis,
        )
        snapshot = rows[0].regeneration_snapshot

        response = self.client.post(
            "/api/v1/analysis/regenerate-simulation/",
            {
                "regeneration_snapshot": snapshot,
                "style_id": rows[0].style_id_snapshot,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")
        self.assertIsNone(response.data["recommendation_id"])
        self.assertEqual(response.data["style_id"], rows[0].style_id_snapshot)
        self.assertEqual(response.data["regeneration_remaining_count"], 0)


class RefreshTokenEndpointTests(APITestCase):
    def test_client_refresh_endpoint_returns_new_tokens(self):
        client = Client.objects.create(name="Client Refresh", phone="01056565656", gender="F")
        refresh_token = build_client_refresh_token(client=client)

        response = self.client.post(
            "/api/v1/auth/refresh/",
            {"refresh_token": refresh_token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["client_id"], client.id)
        self.assertIn("access_token", response.data)
        self.assertIn("refresh_token", response.data)
        self.assertGreater(response.data["refresh_expires_in"], response.data["expires_in"])

    def test_admin_refresh_endpoint_returns_new_tokens(self):
        admin = AdminAccount.objects.create(
            name="Refresh Admin",
            store_name="MirrAI Refresh",
            role="owner",
            phone="01078787878",
            business_number="1234567890",
            password_hash=make_password("plain-password"),
        )
        refresh_token = build_admin_refresh_token(admin=admin)

        response = self.client.post(
            "/api/v1/admin/auth/refresh/",
            {"refresh_token": refresh_token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["admin_id"], admin.id)
        self.assertIn("access_token", response.data)
        self.assertIn("refresh_token", response.data)
        self.assertGreater(response.data["refresh_expires_in"], response.data["expires_in"])
