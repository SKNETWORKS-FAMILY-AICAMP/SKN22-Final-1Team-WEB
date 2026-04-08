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
