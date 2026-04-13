import io
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from app.api.v1 import services_django


class RecommendationDiagnosticSnapshotTests(SimpleTestCase):
    @override_settings(DEBUG=True, MIRRAI_LOCAL_MOCK_RESULTS=True)
    def test_build_snapshot_marks_local_mock_fallback_when_capture_exists_without_analysis(self):
        client = SimpleNamespace(id=7, legacy_client_id="legacy-7", name="Tester", phone="01012345678")
        capture = SimpleNamespace(id=11, status="DONE", face_count=1, created_at=None, updated_at=None)

        with patch.object(services_django, "get_latest_capture_attempt", return_value=capture), patch.object(services_django, "get_latest_survey", return_value=None), patch.object(services_django, "get_latest_capture", return_value=capture), patch.object(services_django, "get_latest_analysis", return_value=None), patch.object(services_django, "get_legacy_former_recommendation_items", return_value=[]), patch.object(services_django, "_has_active_consultation_state", return_value=False), patch.object(services_django, "get_ai_runtime_config_snapshot", return_value={"resolved_provider": "local"}):
            snapshot = services_django.build_recommendation_diagnostic_snapshot(client)

        self.assertTrue(snapshot["capture"]["present"])
        self.assertFalse(snapshot["analysis"]["present"])
        self.assertTrue(snapshot["local_mock_enabled"])
        self.assertEqual(snapshot["predicted_response"]["status"], "ready")
        self.assertEqual(snapshot["predicted_response"]["source"], "local_mock")
        self.assertEqual(snapshot["predicted_response"]["decision"], "local_mock_fallback")
        self.assertIn("missing_analysis", snapshot["predicted_response"]["blockers"])

    def test_get_current_recommendations_emits_structured_resolution_log(self):
        client = SimpleNamespace(id=9, legacy_client_id="legacy-9", name="Logger", phone="01000009999")
        failed_capture = SimpleNamespace(
            status="NEEDS_RETAKE",
            error_note="retake required",
            privacy_snapshot={},
            face_count=0,
            created_at=None,
            updated_at=None,
        )

        with patch.object(services_django, "get_latest_capture_attempt", return_value=failed_capture), patch.object(services_django, "get_latest_survey", return_value=None), patch.object(services_django, "get_latest_capture", return_value=None), patch.object(services_django, "get_latest_analysis", return_value=None), patch.object(services_django, "get_legacy_former_recommendation_items", return_value=[]), patch.object(services_django, "_has_active_consultation_state", return_value=False), patch.object(services_django, "get_ai_runtime_config_snapshot", return_value={"resolved_provider": "local"}), self.assertLogs("app.api.v1.services_django", level="INFO") as captured:
            payload = services_django.get_current_recommendations(client)

        self.assertEqual(payload["status"], "needs_capture")
        self.assertTrue(any("[recommendation_state]" in message for message in captured.output))
        self.assertTrue(any("decision=capture_failed_retake" in message for message in captured.output))

    def test_get_current_recommendations_does_not_mark_ready_when_only_sample_image_exists(self):
        client = SimpleNamespace(id=10, legacy_client_id="legacy-10", name="Regenerator", phone="01000001010")
        latest_capture = SimpleNamespace(id=21, analysis_id=21, status="DONE", face_count=1, created_at=None, updated_at=None)
        latest_analysis = SimpleNamespace(id=21, analysis_id=21, face_shape="oval", golden_ratio_score=0.88, created_at=None)
        current_legacy_items = [
            {
                "analysis_id": 21,
                "batch_id": "batch-old",
                "simulation_image_url": None,
                "synthetic_image_url": None,
                "sample_image_url": "/media/styles/204.jpg",
                "source": "generated",
                "style_id": 204,
                "style_name": "Sleek Mini Bob",
                "style_description": "old batch",
                "keywords": ["bob"],
                "match_score": 70.0,
                "rank": 1,
                "reasoning_snapshot": {"source": "local"},
            }
        ]

        with patch.object(services_django, "get_latest_capture_attempt", return_value=None), patch.object(services_django, "get_latest_survey", return_value=None), patch.object(services_django, "get_latest_capture", return_value=latest_capture), patch.object(services_django, "get_latest_analysis", return_value=latest_analysis), patch.object(services_django, "get_legacy_former_recommendation_items", return_value=current_legacy_items), patch.object(services_django, "_has_active_consultation_state", return_value=False), patch.object(services_django, "get_ai_runtime_config_snapshot", return_value={"resolved_provider": "runpod"}), patch.object(services_django, "persist_simulation_image_reference", side_effect=lambda value: value) as persist_reference, patch.object(services_django, "_ensure_current_batch", return_value=(None, [], "needs_capture")) as ensure_current_batch:
            payload = services_django.get_current_recommendations(client)

        persist_reference.assert_called()
        ensure_current_batch.assert_called_once()
        self.assertNotEqual(payload["status"], "ready")

    def test_get_current_recommendations_waits_for_processing_inputs_before_rendering(self):
        client = SimpleNamespace(id=11, legacy_client_id="legacy-11", name="Waiter", phone="01000001111")
        processing_capture_attempt = SimpleNamespace(status="PROCESSING", error_note=None, created_at=None, updated_at=None)
        ready_capture_attempt = SimpleNamespace(status="DONE", error_note=None, created_at=None, updated_at=None)
        processing_capture = SimpleNamespace(id=31, analysis_id=31, status="PROCESSING", face_count=1, created_at=None, updated_at=None)
        ready_capture = SimpleNamespace(id=31, analysis_id=31, status="DONE", face_count=1, created_at=None, updated_at=None)
        processing_analysis = SimpleNamespace(id=31, analysis_id=31, status="PROCESSING", face_shape=None, golden_ratio_score=None, image_url=None, created_at=None)
        ready_analysis = SimpleNamespace(id=31, analysis_id=31, status="DONE", face_shape="oval", golden_ratio_score=0.91, image_url="/media/analysis-inputs/ready.png", created_at=None)
        ready_items = [
            {
                "analysis_id": 31,
                "batch_id": "batch-ready",
                "simulation_image_url": "/media/simulations/ready.png",
                "synthetic_image_url": "/media/simulations/ready.png",
                "sample_image_url": "/media/styles/201.jpg",
                "source": "generated",
                "style_id": 201,
                "style_name": "Ready Bob",
                "style_description": "ready batch",
                "keywords": ["bob"],
                "match_score": 82.0,
                "rank": 1,
                "reasoning_snapshot": {"source": "local"},
            }
        ]

        with patch.object(services_django, "time") as fake_time, patch.object(services_django, "get_latest_capture_attempt", side_effect=[processing_capture_attempt, ready_capture_attempt]), patch.object(services_django, "get_latest_survey", side_effect=[None, None]), patch.object(services_django, "get_latest_capture", side_effect=[processing_capture, ready_capture]), patch.object(services_django, "get_latest_analysis", side_effect=[processing_analysis, ready_analysis]), patch.object(services_django, "get_legacy_former_recommendation_items", side_effect=[[], ready_items]), patch.object(services_django, "_has_active_consultation_state", return_value=False), patch.object(services_django, "get_ai_runtime_config_snapshot", return_value={"resolved_provider": "runpod"}), patch.object(services_django, "persist_simulation_image_reference", return_value="/media/simulations/ready.png"), patch.object(services_django, "_ensure_current_batch") as ensure_current_batch:
            fake_time.monotonic.side_effect = [0.0, 0.0]
            fake_time.sleep.return_value = None
            payload = services_django.get_current_recommendations(client)

        ensure_current_batch.assert_not_called()
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["batch_id"], "batch-ready")
        self.assertEqual((payload["items"] or [])[0]["simulation_image_url"], "/media/simulations/ready.png")

    def test_get_current_recommendations_waits_for_primary_simulation_image_before_ready(self):
        client = SimpleNamespace(id=12, legacy_client_id="legacy-12", name="ImageWaiter", phone="01000001212")
        latest_capture = SimpleNamespace(id=41, analysis_id=41, status="DONE", face_count=1, created_at=None, updated_at=None)
        latest_analysis = SimpleNamespace(
            id=41,
            analysis_id=41,
            status="DONE",
            face_shape="oval",
            golden_ratio_score=0.93,
            image_url="/media/analysis-inputs/ready.png",
            created_at=None,
        )
        sample_only_items = [
            {
                "analysis_id": 41,
                "batch_id": "batch-sample",
                "simulation_image_url": None,
                "synthetic_image_url": None,
                "sample_image_url": "/media/styles/202.jpg",
                "source": "generated",
                "style_id": 202,
                "style_name": "Sample Bob",
                "style_description": "sample only",
                "keywords": ["bob"],
                "match_score": 74.0,
                "rank": 1,
                "reasoning_snapshot": {"source": "local"},
            }
        ]
        ready_items = [
            {
                "analysis_id": 41,
                "batch_id": "batch-ready",
                "simulation_image_url": "/media/simulations/primary-ready.png",
                "synthetic_image_url": "/media/simulations/primary-ready.png",
                "sample_image_url": "/media/styles/202.jpg",
                "source": "generated",
                "style_id": 202,
                "style_name": "Ready Bob",
                "style_description": "ready",
                "keywords": ["bob"],
                "match_score": 83.0,
                "rank": 1,
                "reasoning_snapshot": {"source": "local"},
            }
        ]

        with patch.object(services_django, "time") as fake_time, patch.object(services_django, "get_latest_capture_attempt", return_value=None), patch.object(services_django, "get_latest_survey", return_value=None), patch.object(services_django, "get_latest_capture", return_value=latest_capture), patch.object(services_django, "get_latest_analysis", return_value=latest_analysis), patch.object(services_django, "get_legacy_former_recommendation_items", side_effect=[sample_only_items, ready_items]), patch.object(services_django, "_has_active_consultation_state", return_value=False), patch.object(services_django, "get_ai_runtime_config_snapshot", return_value={"resolved_provider": "runpod"}), patch.object(services_django, "persist_simulation_image_reference", side_effect=lambda value: value), patch.object(services_django, "_ensure_current_batch") as ensure_current_batch:
            fake_time.monotonic.side_effect = [0.0, 0.0]
            fake_time.sleep.return_value = None
            payload = services_django.get_current_recommendations(client)

        ensure_current_batch.assert_not_called()
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["batch_id"], "batch-ready")
        self.assertEqual((payload["items"] or [])[0]["simulation_image_url"], "/media/simulations/primary-ready.png")

    def test_get_current_recommendations_returns_processing_when_latest_analysis_stays_processing(self):
        client = SimpleNamespace(id=13, legacy_client_id="legacy-13", name="StillProcessing", phone="01000001313")
        latest_capture_attempt = SimpleNamespace(status="PROCESSING", error_note=None, created_at=None, updated_at=None)
        latest_capture = SimpleNamespace(id=51, analysis_id=51, status="PROCESSING", face_count=1, created_at=None, updated_at=None)
        latest_analysis = SimpleNamespace(
            id=51,
            analysis_id=51,
            status="PROCESSING",
            face_shape=None,
            golden_ratio_score=None,
            image_url=None,
            created_at=None,
        )

        with patch.object(services_django, "time") as fake_time, patch.object(services_django, "get_latest_capture_attempt", side_effect=[latest_capture_attempt] * 20), patch.object(services_django, "get_latest_survey", side_effect=[None] * 20), patch.object(services_django, "get_latest_capture", side_effect=[latest_capture] * 20), patch.object(services_django, "get_latest_analysis", side_effect=[latest_analysis] * 20), patch.object(services_django, "get_legacy_former_recommendation_items", side_effect=[[]] * 20), patch.object(services_django, "_has_active_consultation_state", return_value=False), patch.object(services_django, "get_ai_runtime_config_snapshot", return_value={"resolved_provider": "runpod"}):
            fake_time.monotonic.side_effect = [0.0, 0.0, 10.0, 10.0, 30.0, 30.0, 60.0, 60.0, 90.0, 90.0, 120.0]
            fake_time.sleep.return_value = None
            payload = services_django.get_current_recommendations(client)

        self.assertEqual(payload["status"], "processing")

    def test_get_current_recommendations_requires_retake_when_latest_capture_failed(self):
        client = SimpleNamespace(id=14, legacy_client_id="legacy-14", name="Retake", phone="01000001414")
        failed_capture = SimpleNamespace(id=61, analysis_id=61, status="FAILED", face_count=0, created_at=None, updated_at=None)
        failed_analysis = SimpleNamespace(
            id=61,
            analysis_id=61,
            status="FAILED",
            face_shape=None,
            golden_ratio_score=None,
            image_url=None,
            created_at=None,
        )
        sample_only_items = [
            {
                "analysis_id": 61,
                "batch_id": "batch-old",
                "simulation_image_url": None,
                "synthetic_image_url": None,
                "sample_image_url": "/media/styles/204.jpg",
                "source": "generated",
                "style_id": 204,
                "style_name": "Fallback Bob",
                "style_description": "sample only",
                "keywords": ["bob"],
                "match_score": 71.0,
                "rank": 1,
                "reasoning_snapshot": {"source": "local"},
            }
        ]

        with patch.object(services_django, "get_latest_capture_attempt", return_value=failed_capture), patch.object(services_django, "get_latest_survey", return_value=None), patch.object(services_django, "get_latest_capture", return_value=failed_capture), patch.object(services_django, "get_latest_analysis", return_value=failed_analysis), patch.object(services_django, "get_legacy_former_recommendation_items", return_value=sample_only_items), patch.object(services_django, "_has_active_consultation_state", return_value=False), patch.object(services_django, "get_ai_runtime_config_snapshot", return_value={"resolved_provider": "runpod"}):
            payload = services_django.get_current_recommendations(client)

        self.assertEqual(payload["status"], "needs_capture")
        self.assertEqual(payload["items"], [])



class RecommendationDiagnosticCommandTests(SimpleTestCase):
    def _sample_snapshot(self):
        return {
            "client": {
                "client_id": 12,
                "legacy_client_id": "legacy-12",
                "name": "Sample Client",
                "phone": "01011112222",
            },
            "ai_runtime": {
                "configured_provider": "auto",
                "resolved_provider": "runpod",
                "service_enabled": False,
                "runpod_enabled": True,
            },
            "survey": {"present": True, "target_length": "medium", "target_vibe": "chic"},
            "capture_attempt": {"present": True, "status": "DONE", "reason_code": "ok"},
            "capture": {"present": True, "status": "DONE", "record_id": 30},
            "analysis": {"present": True, "face_shape": "Oval", "golden_ratio_score": 0.92},
            "legacy_recommendations": {"count": 0, "latest_batch_id": None, "sources": [], "chosen_count": 0},
            "active_consultation": False,
            "local_mock_enabled": False,
            "predicted_response": {
                "status": "would_generate",
                "source": "current_recommendations",
                "decision": "generate_new_batch",
                "next_actions": ["retry_recommendations", "consultation"],
                "blockers": [],
                "message": "Capture and analysis are ready. Requesting current recommendations would generate a new batch.",
            },
        }

    def test_command_renders_text_report(self):
        stdout = io.StringIO()
        client = SimpleNamespace(id=12, legacy_client_id="legacy-12", name="Sample Client", phone="01011112222")

        with patch("app.management.commands.diagnose_recommendation_state.get_client_by_identifier", return_value=client), patch("app.management.commands.diagnose_recommendation_state.build_recommendation_diagnostic_snapshot", return_value=self._sample_snapshot()):
            call_command("diagnose_recommendation_state", "--client-id", "12", stdout=stdout)

        output = stdout.getvalue()
        self.assertIn("Recommendation diagnostics for client 12 (legacy-12)", output)
        self.assertIn("resolved_provider: runpod", output)
        self.assertIn("decision: generate_new_batch", output)

    def test_command_renders_json_report(self):
        stdout = io.StringIO()
        client = SimpleNamespace(id=12, legacy_client_id="legacy-12", name="Sample Client", phone="01011112222")

        with patch("app.management.commands.diagnose_recommendation_state.get_client_by_identifier", return_value=client), patch("app.management.commands.diagnose_recommendation_state.build_recommendation_diagnostic_snapshot", return_value=self._sample_snapshot()):
            call_command("diagnose_recommendation_state", "--client-id", "12", "--json", stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["client"]["client_id"], 12)
        self.assertEqual(payload["predicted_response"]["decision"], "generate_new_batch")
