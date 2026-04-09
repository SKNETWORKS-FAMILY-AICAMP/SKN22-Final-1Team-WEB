from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from app.services.ai_facade import _AI_HEALTH_CACHE, generate_recommendation_batch, get_ai_health


class RunPodFacadeTests(SimpleTestCase):
    def tearDown(self):
        _AI_HEALTH_CACHE["expires_at"] = 0.0
        _AI_HEALTH_CACHE["payload"] = None

    @patch("app.services.ai_facade.requests.post")
    def test_get_ai_health_prefers_runpod_when_configured(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {
            "output": {
                "status": "ok",
                "cuda": {"available": True, "device": "NVIDIA A40"},
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        with patch.dict(
            "os.environ",
            {
                "MIRRAI_AI_PROVIDER": "runpod",
                "RUNPOD_API_KEY": "test-key",
                "RUNPOD_ENDPOINT_ID": "test-endpoint",
                "MIRRAI_AI_HEALTH_TIMEOUT": "7",
            },
            clear=False,
        ):
            payload = get_ai_health()

        self.assertEqual(payload["mode"], "runpod")
        self.assertEqual(payload["status"], "online")
        self.assertEqual(payload["message"], "NVIDIA A40")
        self.assertEqual(mock_post.call_args.kwargs["timeout"], (3, 7))
        self.assertFalse(payload["cached"])

    @patch("app.services.ai_facade.requests.post")
    def test_get_ai_health_uses_cache_within_cache_window(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {
            "output": {"status": "ok", "cuda": {"device": "NVIDIA A40"}}
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        with patch.dict(
            "os.environ",
            {
                "MIRRAI_AI_PROVIDER": "runpod",
                "RUNPOD_API_KEY": "test-key",
                "RUNPOD_ENDPOINT_ID": "test-endpoint",
                "MIRRAI_AI_HEALTH_CACHE_SECONDS": "30",
            },
            clear=False,
        ):
            first = get_ai_health()
            second = get_ai_health()

        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(mock_post.call_count, 1)

    @patch("app.services.ai_facade.requests.post")
    def test_generate_recommendation_batch_augments_local_items_with_runpod_output(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {
            "output": {
                "results": [
                    {
                        "rank": 0,
                        "clip_score": 0.298,
                        "mask_used": "sam2",
                        "image_base64": "ZmFrZS1pbWFnZQ==",
                        "recommended_style": {"style_name": "Remote Style"},
                    }
                ],
                "elapsed_seconds": 12.3,
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        with patch.dict(
            "os.environ",
            {
                "MIRRAI_AI_PROVIDER": "runpod",
                "RUNPOD_API_KEY": "test-key",
                "RUNPOD_ENDPOINT_ID": "test-endpoint",
            },
            clear=False,
        ):
            items = generate_recommendation_batch(
                client_id=1,
                survey_data={
                    "target_length": "미디엄",
                    "target_vibe": "자연",
                    "scalp_type": "웨이브",
                    "hair_colour": "ash brown",
                    "budget_range": "3만5만",
                },
                analysis_data={
                    "face_shape": "Oval",
                    "golden_ratio_score": 0.92,
                    "image_url": "https://example.com/input.jpg",
                    "landmark_snapshot": {
                        "face_bbox": {"width": 200, "height": 250},
                        "landmarks": {
                            "left_eye": {"point": {"x": 120, "y": 120}},
                            "right_eye": {"point": {"x": 220, "y": 120}},
                            "mouth_center": {"point": {"x": 170, "y": 220}},
                            "chin_center": {"point": {"x": 170, "y": 280}},
                        },
                    },
                },
            )

        self.assertTrue(items)
        self.assertEqual(items[0]["simulation_image_url"], "data:image/png;base64,ZmFrZS1pbWFnZQ==")
        self.assertEqual(items[0]["reasoning_snapshot"]["runpod"]["provider"], "runpod")
