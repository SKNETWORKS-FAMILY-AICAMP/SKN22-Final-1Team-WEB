import base64
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from io import StringIO

from app.api.v1.services_django import (
    _analysis_payload_from_items,
    cancel_style_selection,
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
class AnalysisPayloadPromotionTests(SimpleTestCase):
    def test_analysis_payload_uses_valid_runpod_metadata(self):
        payload = _analysis_payload_from_items(
            items=[
                {
                    "reasoning_snapshot": {
                        "source": "runpod_direct_primary",
                        "runpod": {
                            "face_shape_detected": "oval",
                            "golden_ratio_score": 0.7425,
                        },
                    }
                }
            ],
            fallback_landmark_snapshot={"face_bbox": {"width": 100, "height": 140}},
        )

        self.assertEqual(payload["face_shape"], "oval")
        self.assertEqual(payload["golden_ratio_score"], 0.7425)
        self.assertEqual(payload["analysis_source"], "runpod_direct_primary")

    def test_analysis_payload_falls_back_when_runpod_metadata_is_invalid(self):
        payload = _analysis_payload_from_items(
            items=[
                {
                    "reasoning_snapshot": {
                        "source": "local_scoring_fallback",
                        "face_shape": "square",
                        "ratio_score": 20.0,
                        "runpod": {
                            "face_shape_detected": "not-a-shape",
                            "golden_ratio_score": "invalid",
                        },
                    }
                }
            ],
            fallback_landmark_snapshot={"face_bbox": {"width": 100, "height": 140}},
        )

        self.assertEqual(payload["face_shape"], "square")
        self.assertEqual(payload["golden_ratio_score"], 20.0)
        self.assertEqual(payload["analysis_source"], "local_scoring_fallback")


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

        latest_result = LegacyClientResult.objects.filter(backend_client_ref_id=client.id).order_by("-result_id").first()
        self.assertIsNotNone(latest_result)
        latest_detail = LegacyClientResultDetail.objects.filter(result_id=latest_result.result_id).order_by("rank", "detail_id").first()
        self.assertIsNotNone(latest_detail)
        self.assertEqual(latest_result.analysis_data_snapshot["source"], "runpod_direct_primary")
        self.assertEqual(latest_detail.reasoning_snapshot["source"], "runpod_direct_primary")
        self.assertEqual(
            latest_detail.simulated_image_url,
            "https://example.com/generated-direct.png?expires=1775200000&token=abc",
        )

    def test_persist_generated_batch_propagates_analysis_source_to_reasoning_snapshot(self):
        call_command("seed_test_accounts")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        survey = get_latest_survey(client)
        analysis = get_latest_analysis(client)
        analysis.analysis_source = "local_scoring_fallback"
        precomputed_items = [
            {
                "style_id": 204,
                "style_name": "Sleek Mini Bob",
                "style_description": "source propagation test",
                "keywords": ["bob", "fallback"],
                "sample_image_url": "/media/styles/204.jpg",
                "simulation_image_url": "/media/synthetic/4983_204.jpg",
                "llm_explanation": "fallback explanation",
                "reasoning_snapshot": {"summary": "fallback explanation"},
                "match_score": 70.0,
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

        latest_result = LegacyClientResult.objects.filter(backend_client_ref_id=client.id).order_by("-result_id").first()
        self.assertIsNotNone(latest_result)
        latest_detail = LegacyClientResultDetail.objects.filter(result_id=latest_result.result_id).order_by("rank", "detail_id").first()
        self.assertIsNotNone(latest_detail)
        self.assertEqual(latest_result.analysis_data_snapshot["source"], "local_scoring_fallback")
        self.assertEqual(latest_detail.reasoning_snapshot["source"], "local_scoring_fallback")

    def test_persist_generated_batch_blocks_snapshot_source_mismatch(self):
        call_command("seed_test_accounts")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        survey = get_latest_survey(client)
        analysis = get_latest_analysis(client)
        analysis.analysis_source = "runpod_direct_primary"
        precomputed_items = [
            {
                "style_id": 204,
                "style_name": "Sleek Mini Bob",
                "style_description": "source mismatch test",
                "keywords": ["bob", "fallback"],
                "sample_image_url": "/media/styles/204.jpg",
                "simulation_image_url": "/media/synthetic/4983_204.jpg",
                "llm_explanation": "mismatch explanation",
                "reasoning_snapshot": {
                    "summary": "mismatch explanation",
                    "source": "local_scoring_fallback",
                },
                "match_score": 70.0,
                "rank": 1,
            }
        ]

        with self.assertRaisesMessage(ValueError, "Snapshot source mismatch"):
            persist_generated_batch(
                client=client,
                capture_record=None,
                survey=survey,
                analysis=analysis,
                precomputed_items=precomputed_items,
            )

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

        with patch("app.api.v1.services_django.persist_simulation_image_reference", side_effect=lambda value: "/media/simulations/from-sample.png" if value == "/media/styles/204.jpg" else value):
            persist_generated_batch(
                client=client,
                capture_record=None,
                survey=survey,
                analysis=analysis,
                precomputed_items=mocked_items,
            )

        latest_result = LegacyClientResult.objects.filter(backend_client_ref_id=client.id).order_by("-result_id").first()
        self.assertIsNotNone(latest_result)
        latest_detail = LegacyClientResultDetail.objects.filter(result_id=latest_result.result_id).order_by("rank", "detail_id").first()
        self.assertIsNotNone(latest_detail)
        self.assertEqual(latest_detail.simulated_image_url, "/media/simulations/from-sample.png")
        self.assertEqual(latest_detail.sample_image_url, "/media/styles/204.jpg")

    def test_run_mirrai_analysis_pipeline_fails_with_missing_input_state(self):
        call_command("seed_test_accounts")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        capture_record = create_legacy_capture_upload_record(
            client=client,
            original_path="/media/captures/original.png",
            processed_path="/media/captures/private.processed.jpg",
            filename="capture-missing-input.png",
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
        items_with_missing_input_state = [
            {
                "style_id": 201,
                "style_name": "Side-Parted Lob",
                "style_description": "missing input test",
                "keywords": ["lob"],
                "sample_image_url": "https://example.com/sample-direct.png",
                "simulation_image_url": "https://example.com/generated-direct.png?expires=1775200000&token=abc",
                "llm_explanation": "missing input",
                "reasoning_snapshot": {
                    "summary": "missing input",
                    "runpod_direct": {
                        "status": "skipped",
                        "reason": "missing_required_payload",
                        "invoked": False,
                    },
                },
            }
        ]

        with patch("app.api.v1.services_django.generate_recommendation_batch", return_value=items_with_missing_input_state):
            run_mirrai_analysis_pipeline(capture_record.id)

        analysis_row = LegacyClientAnalysis.objects.filter(backend_capture_record_id=capture_record.id).order_by("-analysis_id").first()
        self.assertIsNotNone(analysis_row)
        self.assertEqual(analysis_row.status, "FAILED")
        self.assertIn("RunPod direct input is missing", analysis_row.error_note)

    def test_run_mirrai_analysis_pipeline_fails_with_runpod_request_failure_state(self):
        call_command("seed_test_accounts")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        capture_record = create_legacy_capture_upload_record(
            client=client,
            original_path="https://example.com/original.png",
            processed_path="https://example.com/processed.png",
            filename="capture-runpod-failed.png",
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
        items_with_failed_request_state = [
            {
                "style_id": 201,
                "style_name": "Side-Parted Lob",
                "style_description": "request failed test",
                "keywords": ["lob"],
                "sample_image_url": "https://example.com/sample-direct.png",
                "simulation_image_url": "https://example.com/generated-direct.png?expires=1775200000&token=abc",
                "llm_explanation": "request failed",
                "reasoning_snapshot": {
                    "summary": "request failed",
                    "runpod_direct": {
                        "status": "failed",
                        "reason": "empty_runpod_response",
                        "invoked": True,
                    },
                },
            }
        ]

        with patch("app.api.v1.services_django.generate_recommendation_batch", return_value=items_with_failed_request_state):
            run_mirrai_analysis_pipeline(capture_record.id)

        analysis_row = LegacyClientAnalysis.objects.filter(backend_capture_record_id=capture_record.id).order_by("-analysis_id").first()
        self.assertIsNotNone(analysis_row)
        self.assertEqual(analysis_row.status, "FAILED")
        self.assertIn("RunPod direct request failed (empty_runpod_response)", analysis_row.error_note)

    def test_confirm_style_selection_materialization_uses_sample_image_when_simulation_ref_is_not_displayable(self):
        call_command("seed_test_accounts")
        shop = get_admin_by_phone(phone="01080001000")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        legacy_item = {
            "recommendation_id": 90002,
            "batch_id": str("4c40d8d4-7140-4dcf-b91d-72795f8f6ae3"),
            "source": "current_recommendations",
            "style_id": 204,
            "style_name": "Sleek Mini Bob",
            "style_description": "materialized sample fallback",
            "keywords": ["mini bob", "sleek"],
            "sample_image_url": "/media/styles/204.jpg",
            "simulation_image_url": "/media/synthetic/non-displayable.png",
            "synthetic_image_url": "/media/synthetic/non-displayable.png",
            "reasoning": "materialized selection",
            "reasoning_snapshot": {"summary": "materialized selection", "source": "generated"},
            "match_score": 88.0,
            "rank": 1,
        }

        existing_result_ids = set(LegacyClientResult.objects.filter(backend_client_ref_id=client.id).values_list("result_id", flat=True))

        def _persist_side_effect(value):
            if value == "/media/styles/204.jpg":
                return "/media/simulations/from-sample.png"
            return value

        with patch("app.api.v1.services_django._legacy_result_and_detail_for_recommendation", return_value=(None, None)), patch("app.api.v1.services_django._legacy_result_and_detail_for_style", return_value=(None, None)), patch("app.api.v1.services_django.get_legacy_former_recommendation_items", return_value=[legacy_item]), patch("app.api.v1.services_django.persist_simulation_image_reference", side_effect=_persist_side_effect):
            payload = confirm_style_selection(
                client=client,
                style_id=204,
                admin_id=get_legacy_admin_id(admin=shop),
                source="current_recommendations",
                direct_consultation=True,
            )

        self.assertEqual(payload["status"], "success")
        new_result = LegacyClientResult.objects.filter(backend_client_ref_id=client.id).exclude(result_id__in=existing_result_ids).order_by("-result_id").first()
        self.assertIsNotNone(new_result)
        new_detail = LegacyClientResultDetail.objects.filter(result_id=new_result.result_id).first()
        self.assertIsNotNone(new_detail)
        self.assertEqual(new_detail.simulated_image_url, "/media/simulations/from-sample.png")
        self.assertIsNone(new_result.selected_image_url)
        self.assertIsNone(new_result.selected_recommendation_id)
        self.assertTrue(new_result.is_active)
        self.assertFalse(new_result.is_confirmed)

    def test_confirm_style_selection_prefers_backend_recommendation_id_as_canonical_key(self):
        call_command("seed_test_accounts")
        shop = get_admin_by_phone(phone="01080001000")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        legacy_item = {
            "recommendation_id": 91234,
            "batch_id": str("4c40d8d4-7140-4dcf-b91d-72795f8f6ae3"),
            "source": "current_recommendations",
            "style_id": 204,
            "style_name": "Sleek Mini Bob",
            "style_description": "canonical key test",
            "keywords": ["mini bob", "sleek"],
            "sample_image_url": "https://example.com/sample.png",
            "simulation_image_url": "https://example.com/generated.png",
            "synthetic_image_url": "https://example.com/generated.png",
            "reasoning": "canonical selection",
            "reasoning_snapshot": {"summary": "canonical selection", "source": "generated"},
            "match_score": 88.0,
            "rank": 1,
        }

        existing_result_ids = set(
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id).values_list("result_id", flat=True)
        )

        with patch("app.api.v1.services_django._legacy_result_and_detail_for_recommendation", return_value=(None, None)), patch("app.api.v1.services_django._legacy_result_and_detail_for_style", return_value=(None, None)), patch("app.api.v1.services_django.get_legacy_former_recommendation_items", return_value=[legacy_item]):
            payload = confirm_style_selection(
                client=client,
                recommendation_id=91234,
                style_id=204,
                admin_id=get_legacy_admin_id(admin=shop),
                source="current_recommendations",
                direct_consultation=False,
            )

        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["recommendation_id"], 91234)
        new_result = (
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id)
            .exclude(result_id__in=existing_result_ids)
            .order_by("-result_id")
            .first()
        )
        self.assertIsNotNone(new_result)
        self.assertEqual(new_result.selected_recommendation_id, 91234)

    def test_direct_consultation_prefers_requested_recommendation_from_current_payload(self):
        call_command("seed_test_accounts")
        shop = get_admin_by_phone(phone="01080001000")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        payload_items = [
            {
                "recommendation_id": 91001,
                "batch_id": str("4c40d8d4-7140-4dcf-b91d-72795f8f6ae3"),
                "source": "current_recommendations",
                "style_id": 204,
                "style_name": "Sleek Mini Bob",
                "style_description": "first item",
                "keywords": ["mini bob"],
                "sample_image_url": "https://example.com/sample-204.png",
                "simulation_image_url": "https://example.com/generated-204.png",
                "synthetic_image_url": "https://example.com/generated-204.png",
                "reasoning": "first",
                "reasoning_snapshot": {"summary": "first", "source": "generated"},
                "match_score": 81.0,
                "rank": 1,
                "is_chosen": False,
            },
            {
                "recommendation_id": 91002,
                "batch_id": str("4c40d8d4-7140-4dcf-b91d-72795f8f6ae3"),
                "source": "current_recommendations",
                "style_id": 205,
                "style_name": "Soft Layered Cut",
                "style_description": "requested item",
                "keywords": ["layered"],
                "sample_image_url": "https://example.com/sample-205.png",
                "simulation_image_url": "https://example.com/generated-205.png",
                "synthetic_image_url": "https://example.com/generated-205.png",
                "reasoning": "requested",
                "reasoning_snapshot": {"summary": "requested", "source": "generated"},
                "match_score": 83.0,
                "rank": 2,
                "is_chosen": False,
            },
        ]
        existing_result_ids = set(
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id).values_list("result_id", flat=True)
        )

        with patch("app.api.v1.services_django._legacy_result_and_detail_for_recommendation", return_value=(None, None)), patch("app.api.v1.services_django._legacy_result_and_detail_for_style", return_value=(None, None)), patch("app.api.v1.services_django.get_legacy_former_recommendation_items", return_value=[]), patch("app.api.v1.services_django.get_current_recommendations", return_value={"items": payload_items}):
            payload = confirm_style_selection(
                client=client,
                recommendation_id=91002,
                admin_id=get_legacy_admin_id(admin=shop),
                source="current_recommendations",
                direct_consultation=True,
            )

        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["selected_style_id"], 205)
        new_result = (
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id)
            .exclude(result_id__in=existing_result_ids)
            .order_by("-result_id")
            .first()
        )
        self.assertIsNotNone(new_result)
        new_detail = LegacyClientResultDetail.objects.filter(result_id=new_result.result_id).first()
        self.assertIsNotNone(new_detail)
        self.assertEqual(new_detail.hairstyle_id, 205)
        self.assertIsNone(new_result.selected_recommendation_id)
        self.assertIsNone(new_result.selected_image_url)

    def test_confirm_style_selection_falls_back_to_style_when_recommendation_lookup_misses(self):
        call_command("seed_test_accounts")
        shop = get_admin_by_phone(phone="01080001000")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        existing_result = (
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id, is_active=True)
            .order_by("-result_id")
            .first()
        )
        self.assertIsNotNone(existing_result)
        existing_detail = (
            LegacyClientResultDetail.objects.filter(result_id=existing_result.result_id)
            .order_by("rank", "detail_id")
            .first()
        )
        self.assertIsNotNone(existing_detail)
        previous_result_count = LegacyClientResult.objects.filter(backend_client_ref_id=client.id).count()

        with patch("app.api.v1.services_django._legacy_result_and_detail_for_recommendation", return_value=(None, None)):
            payload = confirm_style_selection(
                client=client,
                recommendation_id=999999,
                style_id=existing_detail.hairstyle_id,
                admin_id=get_legacy_admin_id(admin=shop),
                source="current_recommendations",
                direct_consultation=False,
            )

        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["selection_record_status"], "linked_generated_style_row")
        self.assertEqual(
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id).count(),
            previous_result_count,
        )

    def test_confirm_style_selection_supports_selected_image_url_only(self):
        call_command("seed_test_accounts")
        shop = get_admin_by_phone(phone="01080001000")
        client_record = LegacyClient.objects.get(phone="01090001003")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        payload_items = [
            {
                "recommendation_id": 92001,
                "batch_id": str("4c40d8d4-7140-4dcf-b91d-72795f8f6ae3"),
                "source": "current_recommendations",
                "style_id": 201,
                "style_name": "French Bob",
                "style_description": "url only selection",
                "keywords": ["bob"],
                "sample_image_url": "https://example.com/sample-201.png",
                "simulation_image_url": "https://example.com/generated-201.png",
                "synthetic_image_url": "https://example.com/generated-201.png",
                "reasoning": "url only",
                "reasoning_snapshot": {"summary": "url only", "source": "generated"},
                "match_score": 80.0,
                "rank": 1,
                "is_chosen": False,
            }
        ]
        existing_result_ids = set(
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id).values_list("result_id", flat=True)
        )

        with patch("app.api.v1.services_django._legacy_result_and_detail_for_recommendation", return_value=(None, None)), patch("app.api.v1.services_django._legacy_result_and_detail_for_style", return_value=(None, None)), patch("app.api.v1.services_django.get_legacy_former_recommendation_items", return_value=[]), patch("app.api.v1.services_django.get_current_recommendations", return_value={"items": payload_items}):
            payload = confirm_style_selection(
                client=client,
                selected_image_url="https://example.com/generated-201.png",
                admin_id=get_legacy_admin_id(admin=shop),
                source="current_recommendations",
                direct_consultation=False,
            )

        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["recommendation_id"], 92001)
        self.assertEqual(payload["selected_style_id"], 201)
        new_result = (
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id)
            .exclude(result_id__in=existing_result_ids)
            .order_by("-result_id")
            .first()
        )
        self.assertIsNotNone(new_result)
        self.assertEqual(new_result.selected_recommendation_id, 92001)
        self.assertEqual(new_result.selected_hairstyle_id, 201)

    def test_cancel_style_selection_supports_selected_image_url_only(self):
        call_command("seed_test_accounts")
        client_record = LegacyClient.objects.get(phone="01090001001")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        active_result = (
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id, is_active=True)
            .order_by("-result_id")
            .first()
        )
        self.assertIsNotNone(active_result)
        active_detail = (
            LegacyClientResultDetail.objects.filter(result_id=active_result.result_id)
            .order_by("rank", "detail_id")
            .first()
        )
        self.assertIsNotNone(active_detail)

        with patch(
            "app.api.v1.services_django.get_legacy_former_recommendation_items",
            return_value=[
                {
                    "recommendation_id": 93001,
                    "style_id": active_detail.hairstyle_id,
                    "simulation_image_url": "https://example.com/generated-cancel.png",
                    "synthetic_image_url": "https://example.com/generated-cancel.png",
                    "sample_image_url": "https://example.com/sample-cancel.png",
                }
            ],
        ):
            payload = cancel_style_selection(
                client=client,
                selected_image_url="https://example.com/generated-cancel.png",
                source="current_recommendations",
            )

        self.assertEqual(payload["status"], "cancelled")
        active_result.refresh_from_db()
        self.assertFalse(active_result.is_active)
        self.assertIsNone(active_result.selected_recommendation_id)

    def test_cancel_style_selection_clears_active_selection_fields(self):
        call_command("seed_test_accounts")
        client_record = LegacyClient.objects.get(phone="01090001001")
        client = get_client_by_identifier(identifier=client_record.backend_client_id)
        active_result = (
            LegacyClientResult.objects.filter(backend_client_ref_id=client.id, is_active=True)
            .order_by("-result_id")
            .first()
        )
        self.assertIsNotNone(active_result)
        active_result.selected_hairstyle_id = 204
        active_result.selected_image_url = "https://example.com/selected.png"
        active_result.selected_recommendation_id = 12345
        active_result.is_confirmed = True
        active_result.save(
            update_fields=[
                "selected_hairstyle_id",
                "selected_image_url",
                "selected_recommendation_id",
                "is_confirmed",
            ]
        )

        payload = cancel_style_selection(client=client, source="current_recommendations")

        self.assertEqual(payload["status"], "cancelled")
        active_result.refresh_from_db()
        self.assertFalse(active_result.is_active)
        self.assertFalse(active_result.is_confirmed)
        self.assertIsNone(active_result.selected_hairstyle_id)
        self.assertIsNone(active_result.selected_image_url)
        self.assertIsNone(active_result.selected_recommendation_id)
