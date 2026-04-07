import io
import json
import os
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase
from fastapi.testclient import TestClient

import main as internal_ai_main
from app.services import ai_facade
from app.services.ai_facade import (
    build_ai_runtime_diagnostic_snapshot,
    build_model_connection_validation_snapshot,
    generate_recommendation_batch,
    get_ai_health,
    get_ai_runtime_config_snapshot,
    simulate_face_analysis,
)


class _MockResponse:
    def __init__(self, *, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"status={self.status_code}")


class AiFacadeContractTests(SimpleTestCase):
    @patch.dict(
        os.environ,
        {
            "MIRRAI_AI_PROVIDER": "service",
            "MIRRAI_AI_SERVICE_URL": "https://mirrai.shop",
            "MIRRAI_INTERNAL_API_TOKEN": "secret-token",
            "MIRRAI_AI_API_VERSION": "2026-04-06",
            "RUNPOD_API_KEY": "legacy-runpod-key",
            "RUNPOD_ENDPOINT_ID": "legacy-runpod-endpoint",
        },
        clear=False,
    )
    @patch("app.services.ai_facade.requests.request")
    def test_get_ai_health_prefers_internal_service_contract(self, mock_request):
        mock_request.return_value = _MockResponse(
            payload={
                "status": "success",
                "schema_version": "2026-04-06",
                "response_version": "1.2.0",
                "request_id": "req-health",
                "processing_time_ms": 12,
                "data": {
                    "role": "ai-microservice",
                    "build_version": "2026.04.06",
                    "model_version": "model-v2",
                    "uptime_seconds": 321,
                },
            }
        )

        payload = get_ai_health(use_cache=False)

        self.assertEqual(payload["mode"], "service")
        self.assertEqual(payload["status"], "online")
        self.assertEqual(payload["message"], "ai-microservice")
        self.assertEqual(payload["build_version"], "2026.04.06")
        self.assertEqual(payload["model_version"], "model-v2")
        self.assertEqual(payload["request_id"], "req-health")

        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs["method"], "GET")
        self.assertTrue(kwargs["url"].endswith("/internal/health"))
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret-token")
        self.assertEqual(kwargs["headers"]["X-MirrAI-API-Version"], "2026-04-06")

    def test_simulate_face_analysis_raises_when_fallback_is_disabled(self):
        with self.assertRaises(RuntimeError) as exc_info:
            simulate_face_analysis(image_url="https://cdn.example.com/original.png")

        self.assertIn("fallback is disabled", str(exc_info.exception))

    @patch.dict(
        os.environ,
        {
            "MIRRAI_AI_PROVIDER": "service",
            "MIRRAI_AI_SERVICE_URL": "https://mirrai.shop",
            "MIRRAI_INTERNAL_API_TOKEN": "secret-token",
        },
        clear=False,
    )
    @patch("app.services.ai_facade.requests.request")
    def test_generate_recommendation_batch_accepts_partial_success_contract(self, mock_request):
        mock_request.return_value = _MockResponse(
            payload={
                "status": "partial_success",
                "schema_version": "2026-04-06",
                "response_version": "1.2.0",
                "request_id": "req-sim",
                "processing_time_ms": 54,
                "partial_failures": [{"style_id": 99, "message": "simulation timeout"}],
                "data": {
                    "items": [
                        {
                            "style_id": 1,
                            "style_name": "Layered Cut",
                            "rank": 1,
                            "score": 0.91,
                            "simulation_image_url": "https://cdn.example.com/sim.png",
                            "reasoning_snapshot": {"summary": "Works well with the face shape and requested mood."},
                        }
                    ]
                },
            }
        )

        items = generate_recommendation_batch(
            client_id=1,
            survey_data={"target_length": "medium"},
            analysis_data={"face_shape": "Oval", "golden_ratio_score": 0.91},
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["style_name"], "Layered Cut")
        self.assertEqual(items[0]["match_score"], 0.91)
        self.assertEqual(items[0]["synthetic_image_url"], "https://cdn.example.com/sim.png")
        self.assertEqual(items[0]["reasoning_snapshot"]["service_status"], "partial_success")
        self.assertEqual(items[0]["reasoning_snapshot"]["partial_failures"][0]["style_id"], 99)
        self.assertEqual(items[0]["response_meta"]["request_id"], "req-sim")


class AiFacadeRunpodDirectTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        ai_facade._AI_HEALTH_CACHE["expires_at"] = 0.0
        ai_facade._AI_HEALTH_CACHE["payload"] = None

    @patch.dict(
        os.environ,
        {
            "RUNPOD_API_KEY": "runpod-key",
            "RUNPOD_ENDPOINT_ID": "",
            "STABLE_DIFFUSION_ENDPOINT": "stable-endpoint",
            "RUNPOD_TRENDS_ENDPOINT_ID": "",
        },
        clear=False,
    )
    def test_runpod_endpoint_id_falls_back_to_stable_diffusion_endpoint(self):
        self.assertEqual(ai_facade._runpod_endpoint_id(), "stable-endpoint")
        self.assertTrue(ai_facade._runpod_enabled())

    @patch.dict(
        os.environ,
        {
            "MIRRAI_AI_PROVIDER": "service",
            "MIRRAI_AI_SERVICE_URL": "",
            "RUNPOD_API_KEY": "runpod-key",
            "RUNPOD_TRENDS_ENDPOINT_ID": "trend-endpoint",
        },
        clear=False,
    )
    def test_service_provider_falls_back_to_runpod_when_service_is_missing(self):
        self.assertEqual(ai_facade._ai_provider(), "runpod")

    @patch.dict(
        os.environ,
        {
            "MIRRAI_AI_PROVIDER": "service",
            "MIRRAI_AI_SERVICE_URL": "",
            "RUNPOD_API_KEY": "runpod-key",
            "RUNPOD_ENDPOINT_ID": "",
            "STABLE_DIFFUSION_ENDPOINT": "stable-endpoint",
            "RUNPOD_TRENDS_ENDPOINT_ID": "",
        },
        clear=False,
    )
    @patch("app.services.ai_facade.requests.post")
    def test_health_check_uses_runpod_when_service_is_not_configured(self, mock_post):
        mock_post.return_value = _MockResponse(
            payload={
                "output": {
                    "status": "COMPLETED",
                    "cuda": {"device": "runpod-gpu"},
                }
            }
        )

        payload = get_ai_health(use_cache=False)

        self.assertEqual(payload["mode"], "runpod")
        self.assertEqual(payload["status"], "online")
        self.assertEqual(payload["message"], "runpod-gpu")

    @patch.dict(
        os.environ,
        {
            "MIRRAI_AI_PROVIDER": "runpod",
            "RUNPOD_API_KEY": "runpod-key",
            "RUNPOD_ENDPOINT_ID": "stable-endpoint",
        },
        clear=False,
    )
    @patch("app.services.ai_facade.requests.post")
    @patch("app.services.ai_facade.score_recommendations")
    def test_runpod_recommendation_metadata_is_attached_to_reasoning_snapshot(self, mock_score_recommendations, mock_post):
        mock_score_recommendations.return_value = [
            {
                "style_id": 201,
                "style_name": "Side-Parted Lob",
                "style_description": "",
                "keywords": ["lob"],
                "match_score": 0.77,
                "rank": 0,
                "reasoning_snapshot": {"summary": "local summary"},
            }
        ]
        mock_post.return_value = _MockResponse(
            payload={
                "output": {
                    "results": [
                        {
                            "rank": 0,
                            "seed": 42,
                            "clip_score": 0.298,
                            "mask_used": "sam2",
                            "image_base64": "ZmFrZS1pbWFnZQ==",
                            "recommended_style": {
                                "style_id": "shaggy-midi",
                                "style_name": "Shaggy Midi Cut",
                                "recommendation_score": 0.8437,
                            },
                        }
                    ],
                    "recommendations": [
                        {
                            "rank": 0,
                            "style_id": "shaggy-midi",
                            "style_name": "Shaggy Midi Cut",
                            "score": 0.8437,
                            "description": "Mid-length shag with crown texture.",
                            "face_shape_detected": "oval",
                            "golden_ratio_score": 0.649,
                            "face_shapes": ["round", "oval", "oblong"],
                        }
                    ],
                    "rag_context": "[자료 1] 제목: shaggy midi",
                    "elapsed_seconds": 58.7,
                    "build_tag": "build-2026-04-06",
                    "runpod": {"endpoint_id": "stable-endpoint"},
                }
            }
        )

        items = generate_recommendation_batch(
            client_id=1,
            survey_data={"target_length": "medium", "target_vibe": "chic"},
            analysis_data={
                "face_shape": "Oval",
                "golden_ratio_score": 0.91,
                "image_url": "https://cdn.example.com/original.png",
                "landmark_snapshot": {
                    "face_bbox": {"width": 100, "height": 140},
                    "landmarks": {
                        "left_eye": {"point": {"x": 20, "y": 40}},
                        "right_eye": {"point": {"x": 80, "y": 40}},
                        "mouth_center": {"point": {"x": 50, "y": 90}},
                        "chin_center": {"point": {"x": 50, "y": 130}},
                    },
                },
            },
        )

        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["simulation_image_url"].startswith("data:image/png;base64,"))
        self.assertEqual(items[0]["llm_explanation"], "Mid-length shag with crown texture.")
        snapshot = items[0]["reasoning_snapshot"]["runpod"]
        self.assertEqual(snapshot["build_tag"], "build-2026-04-06")
        self.assertEqual(snapshot["face_shape_detected"], "oval")
        self.assertEqual(snapshot["golden_ratio_score"], 0.649)
        self.assertEqual(snapshot["runtime"]["endpoint_id"], "stable-endpoint")
        self.assertEqual(snapshot["image_transport"], "base64_data_url")
        self.assertIn("shaggy midi", snapshot["rag_context_excerpt"].lower())

    @patch.dict(
        os.environ,
        {
            "MIRRAI_AI_PROVIDER": "runpod",
            "RUNPOD_API_KEY": "runpod-key",
            "RUNPOD_ENDPOINT_ID": "stable-endpoint",
        },
        clear=False,
    )
    @patch("app.services.ai_facade.requests.post")
    @patch("app.services.ai_facade.score_recommendations")
    def test_runpod_direct_is_primary_when_remote_styles_can_be_mapped(self, mock_score_recommendations, mock_post):
        mock_post.return_value = _MockResponse(
            payload={
                "output": {
                    "results": [
                        {
                            "rank": 0,
                            "clip_score": 0.41,
                            "simulation_image_url": "https://cdn.example.com/sim.png?expires=1775200000&token=abc",
                            "simulation_image_url_expires_at": "2026-04-03T15:20:00Z",
                            "recommended_style": {
                                "style_id": "prada-bob-1",
                                "style_name": "Side-Parted Lob",
                                "recommendation_score": 0.9132,
                            },
                        }
                    ],
                    "recommendations": [
                        {
                            "rank": 0,
                            "style_id": "prada-bob-1",
                            "style_name": "Side-Parted Lob",
                            "score": 0.9132,
                            "description": "Direct recommendation summary.",
                            "face_shape_detected": "oval",
                            "golden_ratio_score": 0.7425,
                            "face_shapes": ["oval", "heart", "oblong"],
                        }
                    ],
                    "runpod": {"endpoint_id": "stable-endpoint"},
                }
            }
        )

        items = generate_recommendation_batch(
            client_id=1,
            survey_data={"target_length": "medium", "target_vibe": "chic"},
            analysis_data={
                "face_shape": "Oval",
                "golden_ratio_score": 0.91,
                "image_url": "https://cdn.example.com/original.png",
                "landmark_snapshot": {
                    "face_bbox": {"width": 100, "height": 140},
                    "landmarks": {
                        "left_eye": {"point": {"x": 20, "y": 40}},
                        "right_eye": {"point": {"x": 80, "y": 40}},
                        "mouth_center": {"point": {"x": 50, "y": 90}},
                        "chin_center": {"point": {"x": 50, "y": 130}},
                    },
                },
            },
            styles_by_id={
                201: SimpleNamespace(
                    name="Side-Parted Lob",
                    style_name="Side-Parted Lob",
                    description="Rounded cheeks are balanced with a longer side silhouette.",
                    image_url="/media/styles/201.jpg",
                    vibe="Chic",
                )
            },
        )

        mock_score_recommendations.assert_not_called()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["style_id"], 201)
        self.assertEqual(items[0]["style_name"], "Side-Parted Lob")
        self.assertEqual(items[0]["sample_image_url"], "/media/styles/201.jpg")
        self.assertEqual(items[0]["simulation_image_url"], "https://cdn.example.com/sim.png?expires=1775200000&token=abc")
        self.assertEqual(items[0]["match_score"], 0.9132)
        self.assertEqual(items[0]["llm_explanation"], "Direct recommendation summary.")
        snapshot = items[0]["reasoning_snapshot"]["runpod"]
        self.assertEqual(snapshot["image_transport"], "signed_url")
        self.assertEqual(snapshot["simulation_image_url_expires_at"], "2026-04-03T15:20:00Z")
        self.assertEqual(snapshot["face_shape_detected"], "oval")

    @patch.dict(
        os.environ,
        {
            "MIRRAI_AI_PROVIDER": "runpod",
            "RUNPOD_API_KEY": "runpod-key",
            "RUNPOD_ENDPOINT_ID": "stable-endpoint",
        },
        clear=False,
    )
    @patch("app.services.ai_facade.requests.post")
    @patch("app.services.ai_facade.score_recommendations")
    def test_runpod_direct_accepts_image_base64_when_image_url_is_absent(self, mock_score_recommendations, mock_post):
        mock_post.return_value = _MockResponse(
            payload={
                "output": {
                    "results": [
                        {
                            "rank": 0,
                            "clip_score": 0.41,
                            "simulation_image_url": "https://cdn.example.com/sim-base64.png?expires=1775200000&token=abc",
                            "recommended_style": {
                                "style_id": "prada-bob-1",
                                "style_name": "Side-Parted Lob",
                                "recommendation_score": 0.9132,
                            },
                        }
                    ],
                    "recommendations": [
                        {
                            "rank": 0,
                            "style_id": "prada-bob-1",
                            "style_name": "Side-Parted Lob",
                            "score": 0.9132,
                            "description": "Base64 direct recommendation summary.",
                            "face_shape_detected": "oval",
                            "golden_ratio_score": 0.7425,
                            "face_shapes": ["oval", "heart", "oblong"],
                        }
                    ],
                    "runpod": {"endpoint_id": "stable-endpoint"},
                }
            }
        )

        items = generate_recommendation_batch(
            client_id=1,
            survey_data={"target_length": "medium", "target_vibe": "chic"},
            analysis_data={
                "face_shape": "Oval",
                "golden_ratio_score": 0.91,
                "image_base64": "ZmFrZS1pbWFnZQ==",
                "landmark_snapshot": {
                    "face_bbox": {"width": 100, "height": 140},
                    "landmarks": {
                        "left_eye": {"point": {"x": 20, "y": 40}},
                        "right_eye": {"point": {"x": 80, "y": 40}},
                        "mouth_center": {"point": {"x": 50, "y": 90}},
                        "chin_center": {"point": {"x": 50, "y": 130}},
                    },
                },
            },
            styles_by_id={
                201: SimpleNamespace(
                    name="Side-Parted Lob",
                    style_name="Side-Parted Lob",
                    description="Rounded cheeks are balanced with a longer side silhouette.",
                    image_url="/media/styles/201.jpg",
                    vibe="Chic",
                )
            },
        )

        mock_score_recommendations.assert_not_called()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["style_id"], 201)
        self.assertEqual(items[0]["simulation_image_url"], "https://cdn.example.com/sim-base64.png?expires=1775200000&token=abc")
        _, kwargs = mock_post.call_args
        request_payload = kwargs["json"]["input"]
        self.assertNotIn("image", request_payload)
        self.assertEqual(request_payload["image_base64"], "ZmFrZS1pbWFnZQ==")

    @patch.dict(
        os.environ,
        {
            "MIRRAI_AI_PROVIDER": "runpod",
            "RUNPOD_API_KEY": "runpod-key",
            "RUNPOD_ENDPOINT_ID": "stable-endpoint",
            "MIRRAI_RUNPOD_SYNC_TIMEOUT": "30",
            "MIRRAI_RUNPOD_POLL_INTERVAL": "0.1",
        },
        clear=False,
    )
    @patch("app.services.ai_facade.time.sleep")
    @patch("app.services.ai_facade.requests.get")
    @patch("app.services.ai_facade.requests.post")
    @patch("app.services.ai_facade.score_recommendations")
    def test_runpod_sync_queue_is_polled_until_completed(self, mock_score_recommendations, mock_post, mock_get, mock_sleep):
        mock_post.return_value = _MockResponse(
            payload={
                "id": "job-123",
                "status": "IN_QUEUE",
            }
        )
        mock_get.return_value = _MockResponse(
            payload={
                "status": "COMPLETED",
                "output": {
                    "results": [
                        {
                            "rank": 0,
                            "clip_score": 0.41,
                            "simulation_image_url": "https://cdn.example.com/sim-polled.png?expires=1775200000&token=abc",
                            "recommended_style": {
                                "style_id": "prada-bob-1",
                                "style_name": "Side-Parted Lob",
                                "recommendation_score": 0.9132,
                            },
                        }
                    ],
                    "recommendations": [
                        {
                            "rank": 0,
                            "style_id": "prada-bob-1",
                            "style_name": "Side-Parted Lob",
                            "score": 0.9132,
                            "description": "Polled direct recommendation summary.",
                            "face_shape_detected": "oval",
                            "golden_ratio_score": 0.7425,
                            "face_shapes": ["oval", "heart", "oblong"],
                        }
                    ],
                    "runpod": {"endpoint_id": "stable-endpoint"},
                },
            }
        )

        items = generate_recommendation_batch(
            client_id=1,
            survey_data={"target_length": "medium", "target_vibe": "chic"},
            analysis_data={
                "face_shape": "Oval",
                "golden_ratio_score": 0.91,
                "image_url": "https://cdn.example.com/original.png",
                "landmark_snapshot": {
                    "face_bbox": {"width": 100, "height": 140},
                    "landmarks": {
                        "left_eye": {"point": {"x": 20, "y": 40}},
                        "right_eye": {"point": {"x": 80, "y": 40}},
                        "mouth_center": {"point": {"x": 50, "y": 90}},
                        "chin_center": {"point": {"x": 50, "y": 130}},
                    },
                },
            },
            styles_by_id={
                201: SimpleNamespace(
                    name="Side-Parted Lob",
                    style_name="Side-Parted Lob",
                    description="Rounded cheeks are balanced with a longer side silhouette.",
                    image_url="/media/styles/201.jpg",
                    vibe="Chic",
                )
            },
        )

        mock_score_recommendations.assert_not_called()
        mock_sleep.assert_not_called()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["style_id"], 201)
        self.assertEqual(items[0]["simulation_image_url"], "https://cdn.example.com/sim-polled.png?expires=1775200000&token=abc")
        self.assertEqual(items[0]["llm_explanation"], "Polled direct recommendation summary.")
        self.assertEqual(mock_get.call_count, 1)
        self.assertIn('/status/job-123', mock_get.call_args.args[0])

    @patch.dict(
        os.environ,
        {
            "MIRRAI_AI_PROVIDER": "runpod",
            "RUNPOD_API_KEY": "runpod-key",
            "RUNPOD_ENDPOINT_ID": "stable-endpoint",
        },
        clear=False,
    )
    @patch("app.services.ai_facade.requests.post")
    @patch("app.services.ai_facade.score_recommendations")
    def test_runpod_signed_url_is_preferred_over_base64_when_available(self, mock_score_recommendations, mock_post):
        mock_score_recommendations.return_value = [
            {
                "style_id": 301,
                "style_name": "Prada Bob",
                "style_description": "",
                "keywords": ["bob"],
                "match_score": 0.88,
                "rank": 0,
                "reasoning_snapshot": {"summary": "local summary"},
            }
        ]
        mock_post.return_value = _MockResponse(
            payload={
                "output": {
                    "results": [
                        {
                            "rank": 0,
                            "clip_score": 0.41,
                            "simulation_image_url": "https://cdn.example.com/sim.png?expires=1775200000&token=abc",
                            "simulation_image_url_expires_at": "2026-04-03T15:20:00Z",
                            "image_base64": "ZmFrZS1pbWFnZQ==",
                            "recommended_style": {
                                "style_id": "prada-bob-1",
                                "style_name": "Prada Bob",
                                "recommendation_score": 0.9132,
                            },
                        }
                    ],
                    "recommendations": [
                        {
                            "rank": 0,
                            "style_id": "prada-bob-1",
                            "style_name": "Prada Bob",
                            "score": 0.9132,
                            "description": "Jaw-length clean bob with compact silhouette.",
                            "face_shape_detected": "oval",
                            "golden_ratio_score": 0.7425,
                            "face_shapes": ["oval", "heart", "oblong"],
                        }
                    ],
                    "runpod": {"endpoint_id": "stable-endpoint"},
                }
            }
        )

        items = generate_recommendation_batch(
            client_id=1,
            survey_data={"target_length": "short", "target_vibe": "chic"},
            analysis_data={
                "face_shape": "Oval",
                "golden_ratio_score": 0.91,
                "image_url": "https://cdn.example.com/original.png",
                "landmark_snapshot": {
                    "face_bbox": {"width": 100, "height": 140},
                    "landmarks": {
                        "left_eye": {"point": {"x": 20, "y": 40}},
                        "right_eye": {"point": {"x": 80, "y": 40}},
                        "mouth_center": {"point": {"x": 50, "y": 90}},
                        "chin_center": {"point": {"x": 50, "y": 130}},
                    },
                },
            },
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["simulation_image_url"], "https://cdn.example.com/sim.png?expires=1775200000&token=abc")
        self.assertEqual(items[0]["synthetic_image_url"], "https://cdn.example.com/sim.png?expires=1775200000&token=abc")
        snapshot = items[0]["reasoning_snapshot"]["runpod"]
        self.assertEqual(snapshot["image_transport"], "signed_url")
        self.assertEqual(snapshot["simulation_image_url_expires_at"], "2026-04-03T15:20:00Z")

    @patch.dict(
        os.environ,
        {
            "MIRRAI_AI_PROVIDER": "runpod",
            "RUNPOD_API_KEY": "runpod-key",
            "RUNPOD_ENDPOINT_ID": "stable-endpoint",
        },
        clear=False,
    )
    @patch("app.services.ai_facade.requests.post")
    @patch("app.services.ai_facade.score_recommendations")
    def test_runpod_direct_maps_style_from_alternative_name_fields(self, mock_score_recommendations, mock_post):
        mock_post.return_value = _MockResponse(
            payload={
                "output": {
                    "results": [
                        {
                            "rank": 0,
                            "clip_score": 0.44,
                            "output": {
                                "generated_image_url": "https://cdn.example.com/sim-alt-name.png?expires=1775200000&token=abc",
                            },
                            "recommended_style": {
                                "name": "Sleek Mini Bob",
                                "recommendation_score": 0.904,
                            },
                            "face_shape": "oval",
                            "golden_ratio": 0.7425,
                        }
                    ],
                    "recommendations": [
                        {
                            "rank": 0,
                            "name": "Sleek Mini Bob",
                            "recommendation_score": 0.904,
                            "reason": "Alternative naming contract summary.",
                        }
                    ],
                    "runpod": {"endpoint_id": "stable-endpoint"},
                }
            }
        )

        items = generate_recommendation_batch(
            client_id=1,
            survey_data={"target_length": "short", "target_vibe": "chic"},
            analysis_data={
                "face_shape": "Oval",
                "golden_ratio_score": 0.91,
                "image_url": "https://cdn.example.com/original.png",
                "landmark_snapshot": {
                    "face_bbox": {"width": 100, "height": 140},
                    "landmarks": {
                        "left_eye": {"point": {"x": 20, "y": 40}},
                        "right_eye": {"point": {"x": 80, "y": 40}},
                        "mouth_center": {"point": {"x": 50, "y": 90}},
                        "chin_center": {"point": {"x": 50, "y": 130}},
                    },
                },
            },
            styles_by_id={
                204: SimpleNamespace(
                    name="Sleek Mini Bob",
                    style_name="Sleek Mini Bob",
                    description="Compact silhouette for strong balance.",
                    image_url="/media/styles/204.jpg",
                    vibe="Chic",
                )
            },
        )

        mock_score_recommendations.assert_not_called()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["style_id"], 204)
        self.assertEqual(items[0]["simulation_image_url"], "https://cdn.example.com/sim-alt-name.png?expires=1775200000&token=abc")
        self.assertEqual(items[0]["llm_explanation"], "Alternative naming contract summary.")
        snapshot = items[0]["reasoning_snapshot"]["runpod"]
        self.assertEqual(snapshot["face_shape_detected"], "oval")
        self.assertEqual(snapshot["golden_ratio_score"], 0.7425)

    @patch.dict(
        os.environ,
        {
            "MIRRAI_AI_PROVIDER": "runpod",
            "RUNPOD_API_KEY": "runpod-key",
            "RUNPOD_ENDPOINT_ID": "stable-endpoint",
        },
        clear=False,
    )
    @patch("app.services.ai_facade.requests.post")
    @patch("app.services.ai_facade.score_recommendations")
    def test_runpod_direct_accepts_results_only_payload(self, mock_score_recommendations, mock_post):
        mock_post.return_value = _MockResponse(
            payload={
                "output": {
                    "results": [
                        {
                            "rank": 0,
                            "simulation": {
                                "image_base64": "ZmFrZS1zaW0=",
                            },
                            "hairstyle": {
                                "hairstyle_name": "Airy Short Bob",
                            },
                            "description": "Results-only response summary.",
                            "face_shape_detected": "round",
                            "golden_ratio_score": 0.688,
                            "recommendation_score": 0.877,
                        }
                    ],
                    "runpod": {"endpoint_id": "stable-endpoint"},
                }
            }
        )

        items = generate_recommendation_batch(
            client_id=1,
            survey_data={"target_length": "short", "target_vibe": "natural"},
            analysis_data={
                "face_shape": "Round",
                "golden_ratio_score": 0.82,
                "image_base64": "ZmFrZS1pbWFnZQ==",
                "landmark_snapshot": {
                    "face_bbox": {"width": 100, "height": 140},
                    "landmarks": {
                        "left_eye": {"point": {"x": 20, "y": 40}},
                        "right_eye": {"point": {"x": 80, "y": 40}},
                        "mouth_center": {"point": {"x": 50, "y": 90}},
                        "chin_center": {"point": {"x": 50, "y": 130}},
                    },
                },
            },
            styles_by_id={
                207: SimpleNamespace(
                    name="Airy Short Bob",
                    style_name="Airy Short Bob",
                    description="Airy volume around the crown.",
                    image_url="/media/styles/207.jpg",
                    vibe="Natural",
                )
            },
        )

        mock_score_recommendations.assert_not_called()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["style_id"], 207)
        self.assertTrue(items[0]["simulation_image_url"].startswith("data:image/png;base64,"))
        snapshot = items[0]["reasoning_snapshot"]["runpod"]
        self.assertEqual(snapshot["face_shape_detected"], "round")
        self.assertEqual(snapshot["golden_ratio_score"], 0.688)


class InternalAiServiceContractTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        internal_ai_main.app.openapi_schema = None

    @patch.dict(os.environ, {"MIRRAI_INTERNAL_API_TOKEN": "internal-secret"}, clear=False)
    def test_internal_health_requires_auth_when_token_is_configured(self):
        with TestClient(internal_ai_main.app) as client:
            response = client.get("/internal/health")

        self.assertEqual(response.status_code, 401)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error_code"], "unauthorized")

    @patch.dict(
        os.environ,
        {
            "MIRRAI_INTERNAL_API_TOKEN": "internal-secret",
            "MIRRAI_AI_BUILD_VERSION": "2026.04.06",
            "MIRRAI_MODEL_VERSION": "model-v2",
        },
        clear=False,
    )
    def test_internal_health_returns_contract_envelope(self):
        with TestClient(internal_ai_main.app) as client:
            response = client.get(
                "/internal/health",
                headers={
                    "Authorization": "Bearer internal-secret",
                    "X-MirrAI-API-Version": "2026-04-06",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["schema_version"], "2026-04-06")
        self.assertEqual(payload["response_version"], "1.2.0")
        self.assertEqual(payload["data"]["role"], "ai-microservice")
        self.assertEqual(payload["data"]["build_version"], "2026.04.06")
        self.assertEqual(payload["data"]["model_version"], "model-v2")
        self.assertEqual(payload["data"]["requested_api_version"], "2026-04-06")

    @patch.dict(os.environ, {"MIRRAI_INTERNAL_API_TOKEN": "internal-secret"}, clear=False)
    @patch("main.score_recommendations")
    def test_generate_simulations_returns_contract_envelope(self, mock_score_recommendations):
        mock_score_recommendations.return_value = [
            {
                "style_id": 7,
                "style_name": "Hush Cut",
                "rank": 1,
                "score": 0.95,
                "simulation_image_url": "https://cdn.example.com/hush.png",
                "reasoning_snapshot": {"summary": "The light texture and volume balance the profile well."},
            }
        ]

        with TestClient(internal_ai_main.app) as client:
            response = client.post(
                "/internal/generate-simulations",
                headers={"Authorization": "Bearer internal-secret"},
                json={
                    "client_id": 1,
                    "survey_data": {"target_length": "medium"},
                    "analysis_data": {"face_shape": "Oval", "golden_ratio_score": 0.92},
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["data"]["items"][0]["style_id"], 7)
        self.assertEqual(payload["data"]["items"][0]["style_name"], "Hush Cut")


class AiRuntimeDiagnosticsTests(SimpleTestCase):
    @patch.dict(
        os.environ,
        {
            "MIRRAI_AI_PROVIDER": "runpod",
            "RUNPOD_API_KEY": "",
            "RUNPOD_ENDPOINT_ID": "",
            "STABLE_DIFFUSION_ENDPOINT": "",
            "RUNPOD_TRENDS_ENDPOINT_ID": "",
        },
        clear=False,
    )
    def test_runtime_config_snapshot_reports_missing_runpod_credentials(self):
        payload = get_ai_runtime_config_snapshot()

        self.assertEqual(payload["configured_provider"], "runpod")
        self.assertFalse(payload["runpod_api_key_configured"])
        self.assertFalse(payload["runpod_endpoint_id_configured"])
        self.assertEqual(payload["resolved_provider"], "local")

    @patch.dict(
        os.environ,
        {
            "MIRRAI_AI_PROVIDER": "service",
            "MIRRAI_AI_SERVICE_URL": "",
            "MIRRAI_INTERNAL_API_TOKEN": "",
            "RUNPOD_API_KEY": "",
            "RUNPOD_ENDPOINT_ID": "",
        },
        clear=False,
    )
    def test_runtime_diagnostic_snapshot_includes_configuration_warnings(self):
        payload = build_ai_runtime_diagnostic_snapshot(use_cache=False)

        self.assertIn("configured_service_but_url_missing", payload["warnings"])
        self.assertIn("configured_service_but_token_missing", payload["warnings"])
        self.assertEqual(payload["health"]["mode"], "local")

    @patch("app.management.commands.diagnose_ai_runtime.build_ai_runtime_diagnostic_snapshot")
    def test_diagnose_ai_runtime_command_renders_json(self, mock_snapshot):
        stdout = io.StringIO()
        mock_snapshot.return_value = {
            "config": {
                "configured_provider": "auto",
                "resolved_provider": "runpod",
                "service_enabled": False,
                "service_url_configured": False,
                "service_token_configured": False,
                "service_api_version": None,
                "runpod_enabled": True,
                "runpod_api_key_configured": True,
                "runpod_endpoint_id_configured": True,
            },
            "health": {
                "mode": "runpod",
                "status": "online",
                "message": "gpu-ok",
                "cached": False,
            },
            "warnings": [],
        }

        call_command("diagnose_ai_runtime", "--json", stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["config"]["resolved_provider"], "runpod")
        self.assertEqual(payload["health"]["status"], "online")

    @patch("app.management.commands.diagnose_ai_runtime.build_ai_runtime_diagnostic_snapshot")
    def test_diagnose_ai_runtime_command_renders_text(self, mock_snapshot):
        stdout = io.StringIO()
        mock_snapshot.return_value = {
            "config": {
                "configured_provider": "service",
                "resolved_provider": "service",
                "service_enabled": True,
                "service_url_configured": True,
                "service_token_configured": True,
                "service_api_version": "2026-04-06",
                "runpod_enabled": False,
                "runpod_api_key_configured": False,
                "runpod_endpoint_id_configured": False,
            },
            "health": {
                "mode": "service",
                "status": "online",
                "message": "ai-microservice",
                "cached": True,
            },
            "warnings": ["service_health_offline"],
        }

        call_command("diagnose_ai_runtime", stdout=stdout)

        output = stdout.getvalue()
        self.assertIn("AI runtime diagnostics", output)
        self.assertIn("resolved_provider: service", output)
        self.assertIn("service_health_offline", output)


    @patch("app.services.ai_facade.get_ai_runtime_config_snapshot")
    @patch("app.services.ai_facade.get_ai_health")
    def test_model_connection_validation_snapshot_reports_unstable_runpod(self, mock_health, mock_config):
        mock_config.return_value = {
            "configured_provider": "runpod",
            "resolved_provider": "runpod",
            "service_enabled": False,
            "service_url_configured": False,
            "service_token_configured": False,
            "service_api_version": None,
            "runpod_enabled": True,
            "runpod_api_key_configured": True,
            "runpod_endpoint_id_configured": True,
        }
        mock_health.side_effect = [
            {"mode": "runpod", "status": "offline", "message": "timeout", "cached": False},
            {"mode": "runpod", "status": "online", "message": "gpu-ok", "cached": False},
            {"mode": "runpod", "status": "online", "message": "gpu-ok", "cached": False},
        ]

        payload = build_model_connection_validation_snapshot(attempts=3, use_cache=False)

        self.assertEqual(payload["summary"]["overall_state"], "unstable")
        self.assertEqual(payload["summary"]["face_analysis_mode"], "runpod_inference_metadata")
        self.assertEqual(payload["summary"]["recommendation_mode"], "runpod_direct_primary_with_sync_polling")
        self.assertIn("runpod_health_flaky", payload["warnings"])

    @patch("app.management.commands.diagnose_ai_runtime.build_model_connection_validation_snapshot")
    def test_diagnose_ai_runtime_command_renders_probe_json(self, mock_snapshot):
        stdout = io.StringIO()
        mock_snapshot.return_value = {
            "config": {
                "configured_provider": "runpod",
                "resolved_provider": "runpod",
                "service_enabled": False,
                "runpod_enabled": True,
            },
            "summary": {
                "attempts": 3,
                "overall_state": "unstable",
                "online_count": 2,
                "offline_count": 1,
                "face_analysis_mode": "runpod_inference_metadata",
                "recommendation_mode": "runpod_direct_primary_with_sync_polling",
                "connectivity_state": "online",
                "inference_status": "unknown",
                "sync_contract_state": "unknown",
                "metadata_state": "unknown",
                "queue_state": "unknown",
                "last_error_code": None,
                "last_error_message": None,
            },
            "probes": [
                {"attempt": 1, "mode": "runpod", "status": "offline", "elapsed_ms": 5012, "message": "timeout"},
                {"attempt": 2, "mode": "runpod", "status": "online", "elapsed_ms": 1034, "message": "gpu-ok"},
            ],
            "warnings": ["runpod_health_flaky"],
        }

        call_command("diagnose_ai_runtime", "--probe", "--json", stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["summary"]["overall_state"], "unstable")
        self.assertEqual(payload["probes"][0]["status"], "offline")

    @patch("app.management.commands.diagnose_ai_runtime.build_model_connection_validation_snapshot")
    def test_diagnose_ai_runtime_command_renders_probe_text(self, mock_snapshot):
        stdout = io.StringIO()
        mock_snapshot.return_value = {
            "config": {
                "configured_provider": "runpod",
                "resolved_provider": "runpod",
                "service_enabled": False,
                "runpod_enabled": True,
            },
            "summary": {
                "attempts": 3,
                "overall_state": "unstable",
                "online_count": 2,
                "offline_count": 1,
                "face_analysis_mode": "runpod_inference_metadata",
                "recommendation_mode": "runpod_direct_primary_with_sync_polling",
                "connectivity_state": "online",
                "inference_status": "unknown",
                "sync_contract_state": "unknown",
                "metadata_state": "unknown",
                "queue_state": "unknown",
                "last_error_code": None,
                "last_error_message": None,
            },
            "probes": [
                {"attempt": 1, "mode": "runpod", "status": "offline", "elapsed_ms": 5012, "message": "timeout"},
                {"attempt": 2, "mode": "runpod", "status": "online", "elapsed_ms": 1034, "message": "gpu-ok"},
            ],
            "warnings": ["runpod_health_flaky"],
        }

        call_command("diagnose_ai_runtime", "--probe", stdout=stdout)

        output = stdout.getvalue()
        self.assertIn("AI model connectivity probe", output)
        self.assertIn("overall_state: unstable", output)
        self.assertIn("face_analysis_mode: runpod_inference_metadata", output)
        self.assertIn("runpod_health_flaky", output)
