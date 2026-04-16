import io
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.utils import timezone

from app.api.v1.django_serializers import SurveySerializer
from app.api.v1 import services_django
from app.front_views import client_recommendation_history_page


class RecommendationDiagnosticSnapshotTests(SimpleTestCase):
    def test_get_former_recommendations_normalizes_image_references_for_history(self):
        client = SimpleNamespace(id=15, legacy_client_id="legacy-15", name="History", phone="01000001515")
        legacy_items = [
            {
                "recommendation_id": 901,
                "sample_image_url": "styles/301.jpg",
                "simulation_image_url": "simulations/301.png",
                "synthetic_image_url": "simulations/301.png",
                "source": "generated",
                "style_id": 301,
                "style_name": "Clean Crop Two-Block",
                "style_description": "history item",
                "keywords": ["crop"],
                "match_score": 82.0,
                "rank": 1,
            }
        ]

        def _resolve(reference):
            mapping = {
                "styles/301.jpg": "https://cdn.example.com/styles/301.jpg",
                "simulations/301.png": "https://cdn.example.com/simulations/301.png",
            }
            return mapping.get(reference, reference)

        with patch.object(services_django, "get_legacy_former_recommendation_items", return_value=legacy_items), patch.object(services_django, "resolve_storage_reference", side_effect=_resolve), patch.object(services_django, "get_legacy_client_id", return_value="legacy-15"):
            payload = services_django.get_former_recommendations(client)

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["sample_image_url"], "https://cdn.example.com/styles/301.jpg")
        self.assertEqual(payload["items"][0]["simulation_image_url"], "https://cdn.example.com/simulations/301.png")
        self.assertEqual(payload["items"][0]["display_image_url"], "https://cdn.example.com/simulations/301.png")

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

    def test_retry_current_recommendations_normalizes_display_image_url_for_preview(self):
        client = SimpleNamespace(id=16, legacy_client_id="legacy-16", name="Retry", phone="01000001616")
        latest_capture = SimpleNamespace(id=71, analysis_id=71, status="DONE", face_count=1, created_at=None, updated_at=None)
        latest_analysis = SimpleNamespace(
            id=71,
            analysis_id=71,
            status="DONE",
            face_shape="oval",
            golden_ratio_score=0.91,
            image_url="analysis/71.png",
            created_at=None,
        )
        latest_survey = SimpleNamespace(id=81)
        initial_items = [
            {
                "analysis_id": 71,
                "batch_id": "batch-initial",
                "simulation_image_url": "simulations/old.png",
                "synthetic_image_url": "simulations/old.png",
                "sample_image_url": "styles/301.jpg",
                "source": "generated",
                "style_id": 301,
                "style_name": "Old Bob",
                "style_description": "initial batch",
                "keywords": ["bob"],
                "match_score": 80.0,
                "rank": 1,
                "reasoning_snapshot": {"recommendation_stage": "initial"},
            }
        ]
        retried_items = [
            {
                "analysis_id": 71,
                "batch_id": "batch-retry",
                "simulation_image_url": "simulations/retry.png",
                "synthetic_image_url": "simulations/retry.png",
                "sample_image_url": "styles/301.jpg",
                "source": "generated",
                "style_id": 301,
                "style_name": "Retry Bob",
                "style_description": "retry batch",
                "keywords": ["bob"],
                "match_score": 84.0,
                "rank": 1,
                "reasoning_snapshot": {"recommendation_stage": "retry"},
            }
        ]

        def _resolve(reference):
            mapping = {
                "styles/301.jpg": "https://cdn.example.com/styles/301.jpg",
                "simulations/old.png": "https://cdn.example.com/simulations/old.png",
                "simulations/retry.png": "https://cdn.example.com/simulations/retry.png",
            }
            return mapping.get(reference, reference)

        with patch.object(services_django, "get_latest_capture", return_value=latest_capture), patch.object(services_django, "get_latest_analysis", return_value=latest_analysis), patch.object(services_django, "get_latest_survey", return_value=latest_survey), patch.object(services_django, "get_legacy_former_recommendation_items", side_effect=[initial_items, retried_items]), patch.object(services_django, "_has_active_consultation_state", return_value=False), patch.object(services_django, "persist_generated_batch", return_value=("batch-retry", None)), patch.object(services_django, "_build_recommendation_diagnostic_snapshot", return_value={"capture": {"record_id": 71}, "analysis": {"analysis_id": 71}, "active_consultation": False}), patch.object(services_django, "resolve_storage_reference", side_effect=_resolve), patch.object(services_django, "get_legacy_client_id", return_value="legacy-16"):
            payload = services_django.retry_current_recommendations(client)

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["batch_id"], "batch-retry")
        self.assertEqual(payload["items"][0]["simulation_image_url"], "https://cdn.example.com/simulations/retry.png")
        self.assertEqual(payload["items"][0]["display_image_url"], "https://cdn.example.com/simulations/retry.png")

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



class RecommendationSurveySnapshotTests(SimpleTestCase):
    def test_normalize_survey_payload_prefers_explicit_gender_branch(self):
        client = SimpleNamespace(id=17, gender="female")

        payload = services_django.normalize_survey_payload(
            client=client,
            payload={
                "gender_branch": "male",
                "q1": "짧게",
                "q2": "확실한 투블럭",
                "q3": "앞머리 올림",
                "q4": "옆가르마",
                "q5": "펌 없이 깔끔하게",
                "q6": "세련된",
            },
        )

        self.assertEqual(payload["gender_branch"], "male")
        self.assertEqual(payload["survey_profile"]["gender_branch"], "male")
        self.assertEqual(payload["target_length"], "short")
        self.assertTrue(payload["question_answers"])
        self.assertEqual(payload["survey_profile"]["style_axes"]["front_styling"], "lifted")
        self.assertEqual(payload["survey_profile"]["style_axes"]["parting"], "side_part")

    def test_build_survey_snapshot_prefers_survey_gender_branch(self):
        client = SimpleNamespace(id=17, gender="female")
        survey = SimpleNamespace(
            target_length="short",
            target_vibe="chic",
            scalp_type="straight",
            hair_colour="black",
            budget_range="mid",
            gender_branch="male",
            preference_vector=[0.1, 0.2],
            survey_profile={"gender_branch": "female"},
            created_at=timezone.now(),
        )

        with patch.object(services_django, "get_latest_survey", return_value=survey), patch.object(
            services_django,
            "build_client_age_profile",
            return_value={},
        ):
            snapshot = services_django.build_survey_snapshot(client)

        self.assertEqual(snapshot["gender_branch"], "male")
        self.assertEqual(snapshot["survey_profile"]["gender_branch"], "male")


class SurveySerializerContractTests(SimpleTestCase):
    def test_survey_serializer_includes_normalized_metadata_fields(self):
        payload = SurveySerializer(
            instance=SimpleNamespace(
                id=41,
                client_id=17,
                target_length="short",
                target_vibe="chic",
                scalp_type="straight",
                hair_colour="brown",
                budget_range="mid",
                gender_branch="male",
                question_answers={"q1": "짧게", "q3": "앞머리 올림", "q4": "옆가르마"},
                survey_profile={
                    "gender_branch": "male",
                    "style_axes": {
                        "front_styling": "lifted",
                        "parting": "side_part",
                    },
                },
                preference_vector=[0.1, 0.2],
            )
        ).data

        self.assertEqual(payload["gender_branch"], "male")
        self.assertTrue(payload["question_answers"])
        self.assertEqual(payload["survey_profile"]["style_axes"]["front_styling"], "lifted")
        self.assertEqual(payload["survey_profile"]["style_axes"]["parting"], "side_part")


class RecommendationHistoryPageTests(SimpleTestCase):
    @override_settings(ROOT_URLCONF="app.urls_front")
    def test_history_page_renders_display_image_url_when_available(self):
        request = RequestFactory().get("/customer/history/")
        request.session = {"customer_id": 15}
        client = SimpleNamespace(id=15, name="History", phone="01000001515")
        history_payload = {
            "items": [
                {
                    "recommendation_id": 901,
                    "style_name": "Clean Crop Two-Block",
                    "style_description": "history item",
                    "display_image_url": "https://cdn.example.com/simulations/301.png",
                    "sample_image_url": "https://cdn.example.com/styles/301.jpg",
                    "match_score": 82.0,
                }
            ],
            "message": "ok",
        }

        with patch("app.front_views.get_session_customer", return_value=client), patch("app.front_views.get_former_recommendations", return_value=history_payload):
            response = client_recommendation_history_page(request)

        self.assertIn('src="https://cdn.example.com/simulations/301.png"', response.content.decode("utf-8"))


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
