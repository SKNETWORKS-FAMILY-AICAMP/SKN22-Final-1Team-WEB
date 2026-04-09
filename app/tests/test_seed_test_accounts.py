import base64
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from io import StringIO

from app.api.v1.services_django import (
    confirm_style_selection,
    get_current_recommendations,
    get_latest_analysis,
    get_latest_survey,
    persist_generated_batch,
    retry_current_recommendations,
    run_mirrai_analysis_pipeline,
)
from app.services.model_team_bridge import (
    create_legacy_capture_upload_record,
    fail_legacy_capture_processing,
    get_admin_by_phone,
    get_client_by_identifier,
    get_legacy_admin_id,
)
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

    def test_persist_generated_batch_converts_base64_simulation_images_to_asset_refs(self):
        with TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir, SUPABASE_USE_REMOTE_STORAGE=False):
                call_command("seed_test_accounts")
                client_record = LegacyClient.objects.get(phone="01090001003")
                client = get_client_by_identifier(identifier=client_record.backend_client_id)
                survey = get_latest_survey(client)
                analysis = get_latest_analysis(client)
                mocked_items = [
                    {
                        "style_id": 201,
                        "style_name": "Side-Parted Lob",
                        "style_description": "generated explanation",
                        "keywords": ["lob"],
                        "sample_image_url": "https://example.com/sample.png",
                        "simulation_image_url": "data:image/png;base64,ZmFrZS1pbWFnZQ==",
                        "llm_explanation": "generated explanation",
                        "reasoning_snapshot": {"summary": "generated explanation"},
                        "match_score": 87.5,
                        "rank": 1,
                    }
                ]

                with patch("app.api.v1.services_django.generate_recommendation_batch", return_value=mocked_items):
                    persist_generated_batch(
                        client=client,
                        capture_record=None,
                        survey=survey,
                        analysis=analysis,
                    )

                latest_result = (
                    LegacyClientResult.objects.filter(backend_client_ref_id=client.id)
                    .order_by("-result_id")
                    .first()
                )
                self.assertIsNotNone(latest_result)
                latest_detail = (
                    LegacyClientResultDetail.objects.filter(result_id=latest_result.result_id)
                    .order_by("rank", "detail_id")
                    .first()
                )
                self.assertIsNotNone(latest_detail)
                self.assertTrue(latest_detail.simulated_image_url.startswith("/media/simulations/"))
                relative_path = latest_detail.simulated_image_url.removeprefix("/media/")
                self.assertTrue((Path(tmpdir) / relative_path).exists())

    def test_persist_generated_batch_preserves_simulation_image_urls(self):
        call_command("seed_test_accounts")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        survey = get_latest_survey(client)
        analysis = get_latest_analysis(client)
        mocked_items = [
            {
                "style_id": 101,
                "style_name": "Codex Bob",
                "style_description": "simulation url preservation test",
                "keywords": ["codex", "test"],
                "sample_image_url": "https://example.com/sample.png",
                "simulation_image_url": "https://example.com/generated.png",
                "llm_explanation": "generated explanation",
                "reasoning_snapshot": {"summary": "generated explanation"},
                "match_score": 87.5,
                "rank": 1,
            }
        ]

        with patch("app.api.v1.services_django.generate_recommendation_batch", return_value=mocked_items):
            persist_generated_batch(
                client=client,
                capture_record=None,
                survey=survey,
                analysis=analysis,
            )

        latest_result = (
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id)
            .order_by("-result_id")
            .first()
        )
        self.assertIsNotNone(latest_result)
        latest_detail = (
            LegacyClientResultDetail.objects.filter(result_id=latest_result.result_id)
            .order_by("rank", "detail_id")
            .first()
        )
        self.assertIsNotNone(latest_detail)
        self.assertEqual(latest_detail.simulated_image_url, "https://example.com/generated.png")
        self.assertEqual(latest_detail.sample_image_url, "https://example.com/sample.png")

    def test_persist_generated_batch_falls_back_to_sample_image_when_simulation_ref_is_not_displayable(self):
        call_command("seed_test_accounts")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        survey = get_latest_survey(client)
        analysis = get_latest_analysis(client)
        mocked_items = [
            {
                "style_id": 204,
                "style_name": "Sleek Mini Bob",
                "style_description": "fallback simulation copy test",
                "keywords": ["bob", "fallback"],
                "sample_image_url": "/media/styles/204.jpg",
                "simulation_image_url": "/media/synthetic/4983_204.jpg",
                "llm_explanation": "fallback explanation",
                "reasoning_snapshot": {"summary": "fallback explanation"},
                "match_score": 77.7,
                "rank": 1,
            }
        ]

        persist_generated_batch(
            client=client,
            capture_record=None,
            survey=survey,
            analysis=analysis,
            precomputed_items=mocked_items,
        )

        latest_result = (
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id)
            .order_by("-result_id")
            .first()
        )
        self.assertIsNotNone(latest_result)
        latest_detail = (
            LegacyClientResultDetail.objects.filter(result_id=latest_result.result_id)
            .order_by("rank", "detail_id")
            .first()
        )
        self.assertIsNotNone(latest_detail)
        self.assertTrue(str(latest_detail.simulated_image_url or "").startswith("/media/simulations/"))
        relative_path = str(latest_detail.simulated_image_url or "").removeprefix("/media/")
        self.assertTrue((Path("storage") / relative_path).exists())

    def test_create_legacy_capture_upload_record_uses_shop_designer_when_client_is_unassigned(self):
        call_command("seed_test_accounts")
        client_record = LegacyClient.objects.get(phone="01090001004")
        self.assertIsNone(client_record.backend_designer_ref_id)
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        self.assertIsNotNone(client)

        capture_record = create_legacy_capture_upload_record(
            client=client,
            original_path=None,
            processed_path=None,
            filename="capture-unassigned.png",
            status="PENDING",
            face_count=1,
            landmark_snapshot={"face_bbox": {"width": 100, "height": 140}},
            deidentified_path=None,
            privacy_snapshot={"storage_policy": "vector_only"},
            error_note=None,
        )

        analysis_row = LegacyClientAnalysis.objects.get(analysis_id=capture_record.id)
        expected_designer = LegacyDesigner.objects.get(designer_id=analysis_row.designer_id)
        self.assertFalse(expected_designer.is_active)
        self.assertEqual(expected_designer.backend_shop_ref_id, client.shop_id)
        self.assertEqual(expected_designer.name or expected_designer.designer_name, "Unassigned Capture")
        self.assertEqual(str(analysis_row.client_id), str(client_record.client_id))
        self.assertEqual(str(analysis_row.designer_id), str(expected_designer.designer_id))
        self.assertIsNone(analysis_row.backend_designer_ref_id)

    def test_persist_generated_batch_records_runpod_direct_primary_source(self):
        call_command("seed_test_accounts")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        survey = get_latest_survey(client)
        analysis = get_latest_analysis(client)
        analysis.analysis_source = "runpod_direct_primary"
        precomputed_items = [
            {
                "style_id": 201,
                "style_name": "Side-Parted Lob",
                "style_description": "direct primary persistence test",
                "keywords": ["lob", "direct"],
                "sample_image_url": "https://example.com/sample-direct.png",
                "simulation_image_url": "https://example.com/generated-direct.png?expires=1775200000&token=abc",
                "llm_explanation": "direct explanation",
                "reasoning_snapshot": {
                    "summary": "direct explanation",
                    "source": "runpod_direct_primary",
                    "runpod": {
                        "provider": "runpod",
                        "face_shape_detected": "oval",
                        "golden_ratio_score": 0.7425,
                    },
                },
                "match_score": 91.32,
                "rank": 1,
            }
        ]

        persist_generated_batch(
            client=client,
            capture_record=None,
            survey=survey,
            analysis=analysis,
            precomputed_items=precomputed_items,
        )

        latest_result = (
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id)
            .order_by("-result_id")
            .first()
        )
        self.assertIsNotNone(latest_result)
        latest_detail = (
            LegacyClientResultDetail.objects.filter(result_id=latest_result.result_id)
            .order_by("rank", "detail_id")
            .first()
        )
        self.assertIsNotNone(latest_detail)
        self.assertEqual(latest_result.analysis_data_snapshot["source"], "runpod_direct_primary")
        self.assertEqual(latest_detail.reasoning_snapshot["source"], "runpod_direct_primary")
        self.assertEqual(
            latest_detail.simulated_image_url,
            "https://example.com/generated-direct.png?expires=1775200000&token=abc",
        )

    def test_run_mirrai_analysis_pipeline_uses_runpod_direct_before_face_analysis_fallback(self):
        call_command("seed_test_accounts")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        capture_record = create_legacy_capture_upload_record(
            client=client,
            original_path="https://example.com/original.png",
            processed_path="https://example.com/processed.png",
            filename="capture.png",
            status="PENDING",
            face_count=1,
            landmark_snapshot={
                "face_bbox": {"width": 100, "height": 140},
                "landmarks": {
                    "left_eye": {"point": {"x": 20, "y": 40}},
                    "right_eye": {"point": {"x": 80, "y": 40}},
                    "mouth_center": {"point": {"x": 50, "y": 90}},
                    "chin_center": {"point": {"x": 50, "y": 130}},
                },
            },
            deidentified_path=None,
            privacy_snapshot={"storage_policy": "ephemeral"},
            error_note=None,
        )
        direct_items = [
            {
                "style_id": 201,
                "style_name": "Side-Parted Lob",
                "style_description": "direct primary pipeline test",
                "keywords": ["lob", "direct"],
                "sample_image_url": "https://example.com/sample-direct.png",
                "simulation_image_url": "https://example.com/generated-direct.png?expires=1775200000&token=abc",
                "llm_explanation": "direct pipeline explanation",
                "reasoning_snapshot": {
                    "summary": "direct pipeline explanation",
                    "source": "runpod_direct_primary",
                    "runpod": {
                        "provider": "runpod",
                        "face_shape_detected": "oval",
                        "golden_ratio_score": 0.7425,
                    },
                },
                "match_score": 91.32,
                "rank": 1,
            }
        ]

        with patch("app.api.v1.services_django.generate_recommendation_batch", return_value=direct_items) as mock_generate:
            run_mirrai_analysis_pipeline(record_id=capture_record.id)

        mock_generate.assert_called_once()
        _, kwargs = mock_generate.call_args
        self.assertEqual(kwargs["analysis_data"]["image_url"], "https://example.com/processed.png")
        self.assertIsNone(kwargs["analysis_data"]["image_base64"])
        analysis_row = (
            LegacyClientAnalysis.objects.filter(backend_capture_record_id=capture_record.id)
            .order_by("-analysis_id")
            .first()
        )
        self.assertIsNotNone(analysis_row)
        self.assertEqual(analysis_row.status, "DONE")
        self.assertEqual(analysis_row.face_type, "oval")
        self.assertEqual(float(analysis_row.golden_ratio_score), 0.7425)
        latest_result = (
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id)
            .order_by("-result_id")
            .first()
        )
        self.assertIsNotNone(latest_result)
        latest_detail = (
            LegacyClientResultDetail.objects.filter(result_id=latest_result.result_id)
            .order_by("rank", "detail_id")
            .first()
        )
        self.assertIsNotNone(latest_detail)
        self.assertEqual(latest_result.analysis_data_snapshot["source"], "runpod_direct_primary")
        self.assertEqual(latest_detail.reasoning_snapshot["source"], "runpod_direct_primary")

    def test_run_mirrai_analysis_pipeline_uses_processed_bytes_for_vector_only_capture(self):
        call_command("seed_test_accounts")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        capture_record = create_legacy_capture_upload_record(
            client=client,
            original_path=None,
            processed_path=None,
            filename="capture-vector-only.png",
            status="PENDING",
            face_count=1,
            landmark_snapshot={
                "face_bbox": {"width": 100, "height": 140},
                "landmarks": {
                    "left_eye": {"point": {"x": 20, "y": 40}},
                    "right_eye": {"point": {"x": 80, "y": 40}},
                    "mouth_center": {"point": {"x": 50, "y": 90}},
                    "chin_center": {"point": {"x": 50, "y": 130}},
                },
            },
            deidentified_path=None,
            privacy_snapshot={"storage_policy": "vector_only"},
            error_note=None,
        )
        direct_items = [
            {
                "style_id": 201,
                "style_name": "Side-Parted Lob",
                "style_description": "vector only direct test",
                "keywords": ["lob", "direct"],
                "sample_image_url": "https://example.com/sample-direct.png",
                "simulation_image_url": "https://example.com/generated-vector-only.png?expires=1775200000&token=abc",
                "llm_explanation": "vector only direct explanation",
                "reasoning_snapshot": {
                    "summary": "vector only direct explanation",
                    "source": "runpod_direct_primary",
                    "runpod": {
                        "provider": "runpod",
                        "face_shape_detected": "oval",
                        "golden_ratio_score": 0.7425,
                    },
                },
                "match_score": 91.32,
                "rank": 1,
            }
        ]
        processed_bytes = b"vector-only-jpeg-bytes"

        with patch("app.api.v1.services_django.generate_recommendation_batch", return_value=direct_items) as mock_generate:
            run_mirrai_analysis_pipeline(record_id=capture_record.id, processed_bytes=processed_bytes)

        mock_generate.assert_called_once()
        _, kwargs = mock_generate.call_args
        self.assertIsNone(kwargs["analysis_data"]["image_url"])
        self.assertEqual(
            kwargs["analysis_data"]["image_base64"],
            base64.b64encode(processed_bytes).decode("ascii"),
        )
        analysis_row = (
            LegacyClientAnalysis.objects.filter(backend_capture_record_id=capture_record.id)
            .order_by("-analysis_id")
            .first()
        )
        self.assertIsNotNone(analysis_row)
        self.assertEqual(analysis_row.status, "DONE")
        self.assertTrue(str(analysis_row.analysis_image_url or "").startswith("/media/analysis-inputs/"))
        latest_result = (
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id)
            .order_by("-result_id")
            .first()
        )
        self.assertIsNotNone(latest_result)
        self.assertEqual(latest_result.analysis_data_snapshot["source"], "runpod_direct_primary")

    def test_run_mirrai_analysis_pipeline_blocks_internal_media_path_from_runpod_input(self):
        call_command("seed_test_accounts")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        capture_record = create_legacy_capture_upload_record(
            client=client,
            original_path="/media/captures/original.png",
            processed_path="/media/captures/private.processed.jpg",
            filename="capture-internal-media.png",
            status="PENDING",
            face_count=1,
            landmark_snapshot={
                "face_bbox": {"width": 100, "height": 140},
                "landmarks": {
                    "left_eye": {"point": {"x": 20, "y": 40}},
                    "right_eye": {"point": {"x": 80, "y": 40}},
                    "mouth_center": {"point": {"x": 50, "y": 90}},
                    "chin_center": {"point": {"x": 50, "y": 130}},
                },
            },
            deidentified_path=None,
            privacy_snapshot={"storage_policy": "ephemeral"},
            error_note=None,
        )
        direct_items = [
            {
                "style_id": 201,
                "style_name": "Side-Parted Lob",
                "style_description": "internal media block test",
                "keywords": ["lob", "direct"],
                "sample_image_url": "https://example.com/sample-direct.png",
                "simulation_image_url": "https://example.com/generated-direct.png?expires=1775200000&token=abc",
                "llm_explanation": "internal media block explanation",
                "reasoning_snapshot": {
                    "summary": "internal media block explanation",
                    "source": "runpod_direct_primary",
                    "runpod": {
                        "provider": "runpod",
                        "face_shape_detected": "oval",
                        "golden_ratio_score": 0.7425,
                    },
                },
                "match_score": 91.32,
                "rank": 1,
            }
        ]

        with patch("app.api.v1.services_django.generate_recommendation_batch", return_value=direct_items) as mock_generate:
            run_mirrai_analysis_pipeline(record_id=capture_record.id)

        mock_generate.assert_called_once()
        _, kwargs = mock_generate.call_args
        self.assertIsNone(kwargs["analysis_data"]["image_url"])
        self.assertIsNone(kwargs["analysis_data"]["image_base64"])
        analysis_row = (
            LegacyClientAnalysis.objects.filter(backend_capture_record_id=capture_record.id)
            .order_by("-analysis_id")
            .first()
        )
        self.assertIsNotNone(analysis_row)
        self.assertEqual(analysis_row.status, "DONE")
        self.assertTrue(str(analysis_row.analysis_image_url or "").startswith("/media/"))

    def test_run_mirrai_analysis_pipeline_fails_when_runpod_metadata_is_missing(self):
        call_command("seed_test_accounts")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        capture_record = create_legacy_capture_upload_record(
            client=client,
            original_path="https://example.com/original.png",
            processed_path="https://example.com/processed.png",
            filename="capture-missing-meta.png",
            status="PENDING",
            face_count=1,
            landmark_snapshot={
                "face_bbox": {"width": 100, "height": 140},
                "landmarks": {
                    "left_eye": {"point": {"x": 20, "y": 40}},
                    "right_eye": {"point": {"x": 80, "y": 40}},
                    "mouth_center": {"point": {"x": 50, "y": 90}},
                    "chin_center": {"point": {"x": 50, "y": 130}},
                },
            },
            deidentified_path=None,
            privacy_snapshot={"storage_policy": "ephemeral"},
            error_note=None,
        )
        items_without_runpod_metadata = [
            {
                "style_id": 201,
                "style_name": "Side-Parted Lob",
                "style_description": "metadata missing test",
                "keywords": ["lob"],
                "sample_image_url": "https://example.com/sample-direct.png",
                "simulation_image_url": "https://example.com/generated-direct.png?expires=1775200000&token=abc",
                "llm_explanation": "metadata missing",
                "reasoning_snapshot": {
                    "summary": "metadata missing",
                    "source": "runpod_direct_primary",
                },
                "match_score": 91.32,
                "rank": 1,
            }
        ]

        with patch("app.api.v1.services_django.generate_recommendation_batch", return_value=items_without_runpod_metadata):
            run_mirrai_analysis_pipeline(record_id=capture_record.id)

        analysis_row = (
            LegacyClientAnalysis.objects.filter(backend_capture_record_id=capture_record.id)
            .order_by("-analysis_id")
            .first()
        )
        self.assertIsNotNone(analysis_row)
        self.assertEqual(analysis_row.status, "FAILED")
        self.assertIn("RunPod direct metadata is missing", analysis_row.error_note)
        self.assertFalse(
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id, analysis_id=analysis_row.analysis_id).exists()
        )

    def test_run_mirrai_analysis_pipeline_persists_local_scoring_fallback_when_runpod_direct_fails(self):
        call_command("seed_test_accounts")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        capture_record = create_legacy_capture_upload_record(
            client=client,
            original_path=None,
            processed_path=None,
            filename="capture-local-fallback.png",
            status="PENDING",
            face_count=1,
            landmark_snapshot={
                "face_bbox": {"width": 100, "height": 140},
                "landmarks": {
                    "left_eye": {"point": {"x": 20, "y": 40}},
                    "right_eye": {"point": {"x": 80, "y": 40}},
                    "mouth_center": {"point": {"x": 50, "y": 90}},
                    "chin_center": {"point": {"x": 50, "y": 130}},
                },
            },
            deidentified_path=None,
            privacy_snapshot={"storage_policy": "vector_only"},
            error_note=None,
        )
        local_fallback_items = [
            {
                "style_id": 204,
                "style_name": "Sleek Mini Bob",
                "style_description": "local scoring fallback test",
                "keywords": ["bob", "fallback"],
                "sample_image_url": "/media/styles/204.jpg",
                "simulation_image_url": "/media/synthetic/4983_204.jpg",
                "llm_explanation": "local fallback explanation",
                "reasoning": "face 18.0/40 | ratio 20.0/20 | preference 32.0/40",
                "reasoning_snapshot": {
                    "summary": "face 18.0/40 | ratio 20.0/20 | preference 32.0/40",
                    "face_shape": "square",
                    "ratio_mode": "balanced",
                    "face_score": 18.0,
                    "ratio_score": 20.0,
                    "preference_score": 32.0,
                    "penalty": 0.0,
                    "total_score": 70.0,
                    "matched_labels": ["length"],
                    "style_keywords": ["bob", "fallback"],
                    "scoring_profile": "initial",
                    "scoring_weights": {"face_weight": 40.0, "ratio_weight": 20.0, "preference_weight": 40.0, "profile": "initial"},
                },
                "match_score": 70.0,
                "rank": 1,
            }
        ]

        with patch("app.api.v1.services_django.generate_recommendation_batch", return_value=local_fallback_items):
            run_mirrai_analysis_pipeline(record_id=capture_record.id, processed_bytes=b"vector-only-jpeg-bytes")

        analysis_row = (
            LegacyClientAnalysis.objects.filter(backend_capture_record_id=capture_record.id)
            .order_by("-analysis_id")
            .first()
        )
        self.assertIsNotNone(analysis_row)
        self.assertEqual(analysis_row.status, "DONE")
        self.assertTrue(str(analysis_row.analysis_image_url or "").startswith("/media/analysis-inputs/"))
        latest_result = (
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id)
            .order_by("-result_id")
            .first()
        )
        self.assertIsNotNone(latest_result)
        latest_detail = (
            LegacyClientResultDetail.objects.filter(result_id=latest_result.result_id)
            .order_by("rank", "detail_id")
            .first()
        )
        self.assertIsNotNone(latest_detail)
        self.assertTrue(str(latest_detail.simulated_image_url or "").startswith("/media/simulations/"))

    def test_get_current_recommendations_does_not_reuse_stale_batch_after_failed_capture(self):
        call_command("seed_test_accounts")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)

        capture_record = create_legacy_capture_upload_record(
            client=client,
            original_path=None,
            processed_path=None,
            filename="capture-failed-after-batch.png",
            status="PENDING",
            face_count=1,
            landmark_snapshot={"face_bbox": {"width": 100, "height": 140}},
            deidentified_path=None,
            privacy_snapshot={"storage_policy": "vector_only"},
            error_note=None,
        )
        fail_legacy_capture_processing(
            record_id=capture_record.id,
            error_note="RunPod direct metadata is missing from recommendation output; capture analysis cannot continue.",
        )

        payload = get_current_recommendations(client)
        self.assertEqual(payload["status"], "needs_capture")
        self.assertEqual(payload["items"], [])
        self.assertIn("RunPod direct metadata is missing", payload["message"])

    def test_retry_current_recommendations_rejects_stale_batch_after_failed_capture(self):
        call_command("seed_test_accounts")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)

        capture_record = create_legacy_capture_upload_record(
            client=client,
            original_path=None,
            processed_path=None,
            filename="capture-failed-before-retry.png",
            status="PENDING",
            face_count=1,
            landmark_snapshot={"face_bbox": {"width": 100, "height": 140}},
            deidentified_path=None,
            privacy_snapshot={"storage_policy": "vector_only"},
            error_note=None,
        )
        fail_legacy_capture_processing(
            record_id=capture_record.id,
            error_note="RunPod direct metadata is missing from recommendation output; capture analysis cannot continue.",
        )

        with self.assertRaises(ValueError) as exc_info:
            retry_current_recommendations(client)

        self.assertIn("RunPod direct metadata is missing", str(exc_info.exception))

    def test_confirm_style_selection_persists_selected_image_url(self):
        call_command("seed_test_accounts")
        shop = get_admin_by_phone(phone="01080001000")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)

        target_result = (
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id)
            .order_by("-result_id")
            .first()
        )
        self.assertIsNotNone(target_result)
        target_detail = (
            LegacyClientResultDetail.objects.filter(result_id=target_result.result_id)
            .order_by("rank", "detail_id")
            .first()
        )
        self.assertIsNotNone(target_detail)
        target_detail.simulated_image_url = "https://example.com/selected-simulation.png"
        target_detail.save(update_fields=["simulated_image_url"])

        confirm_style_selection(
            client=client,
            recommendation_id=target_detail.detail_id,
            admin_id=get_legacy_admin_id(admin=shop),
            source="current_recommendations",
        )

        target_result.refresh_from_db()
        target_detail.refresh_from_db()
        self.assertEqual(target_result.selected_image_url, "https://example.com/selected-simulation.png")
        self.assertTrue(target_detail.is_chosen)

    def test_confirm_style_selection_materializes_current_recommendation_when_legacy_row_is_missing(self):
        call_command("seed_test_accounts")
        shop = get_admin_by_phone(phone="01080001000")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        latest_analysis = get_latest_analysis(client)
        legacy_item = {
            "recommendation_id": 90001,
            "batch_id": str("96127dda-e76c-4afc-ab5c-4a458b06e5d1"),
            "source": "current_recommendations",
            "style_id": 204,
            "style_name": "Sleek Mini Bob",
            "style_description": "materialized from current recommendation",
            "keywords": ["mini bob", "sleek"],
            "sample_image_url": "/media/styles/204.jpg",
            "simulation_image_url": "/media/simulations/materialized-selection.png",
            "synthetic_image_url": "/media/simulations/materialized-selection.png",
            "reasoning": "materialized selection",
            "reasoning_snapshot": {"summary": "materialized selection", "source": "generated"},
            "match_score": 88.0,
            "rank": 1,
        }

        existing_result_ids = set(
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id).values_list("result_id", flat=True)
        )

        with patch("app.api.v1.services_django._legacy_result_and_detail_for_recommendation", return_value=(None, None)), patch("app.api.v1.services_django._legacy_result_and_detail_for_style", return_value=(None, None)), patch("app.api.v1.services_django.get_legacy_former_recommendation_items", return_value=[legacy_item]), patch("app.api.v1.services_django.persist_simulation_image_reference", side_effect=lambda value: value):
            payload = confirm_style_selection(
                client=client,
                style_id=204,
                admin_id=get_legacy_admin_id(admin=shop),
                source="current_recommendations",
                direct_consultation=True,
            )

        self.assertEqual(payload["status"], "success")
        new_result = (
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id)
            .exclude(result_id__in=existing_result_ids)
            .order_by("-result_id")
            .first()
        )
        self.assertIsNotNone(new_result)
        self.assertEqual(new_result.analysis_id, getattr(latest_analysis, "analysis_id", latest_analysis.id))
        self.assertIsNone(new_result.selected_hairstyle_id)
        new_detail = LegacyClientResultDetail.objects.filter(result_id=new_result.result_id).first()
        self.assertIsNotNone(new_detail)
        self.assertEqual(new_detail.style_name_snapshot, "Sleek Mini Bob")
        self.assertEqual(new_detail.simulated_image_url, "/media/simulations/materialized-selection.png")

    def test_legacy_customer_detail_exposes_final_selected_style(self):
        call_command("seed_test_accounts")
        shop = get_admin_by_phone(phone="01080001000")
        self._login_shop_session(shop)
        client_record = LegacyClient.objects.get(phone="01090001001")
        chosen_detail = (
            LegacyClientResultDetail.objects.filter(
                backend_client_ref_id=client_record.backend_client_id,
                is_chosen=True,
            )
            .order_by("-detail_id")
            .first()
        )
        self.assertIsNotNone(chosen_detail)
        chosen_detail.simulated_image_url = "https://example.com/final-selected.png"
        chosen_detail.save(update_fields=["simulated_image_url"])

        response = self.client.get(f"/api/v1/customers/{client_record.backend_client_id}/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("final_selected_style", payload)
        self.assertIsNotNone(payload["final_selected_style"])
        self.assertEqual(
            payload["final_selected_style"]["simulation_image_url"],
            "https://example.com/final-selected.png",
        )
        self.assertTrue(payload["final_selected_style"]["is_chosen"])

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
