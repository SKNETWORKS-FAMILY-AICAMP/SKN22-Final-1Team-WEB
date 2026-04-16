from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from app.services.ai_facade import _AI_HEALTH_CACHE, _post_runpod, generate_recommendation_batch, get_ai_health


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
        self.assertEqual(items[0]["simulation_image_url"], "data:image/jpeg;base64,ZmFrZS1pbWFnZQ==")
        self.assertEqual(items[0]["reasoning_snapshot"]["runpod"]["provider"], "runpod")

    @patch("app.services.ai_facade.requests.get")
    @patch("app.services.ai_facade.requests.post")
    def test_post_runpod_polls_status_until_output_is_ready(self, mock_post, mock_get):
        initial_response = Mock()
        initial_response.json.return_value = {
            "id": "job-123",
            "status": "IN_PROGRESS",
        }
        initial_response.raise_for_status.return_value = None
        mock_post.return_value = initial_response

        status_response = Mock()
        status_response.json.return_value = {
            "id": "job-123",
            "status": "COMPLETED",
            "output_url": "https://example.com/output/job-123",
        }
        status_response.raise_for_status.return_value = None

        output_response = Mock()
        output_response.json.return_value = {
            "output": {
                "results": [
                    {
                        "rank": 0,
                        "image_base64": "ZmFrZS1pbWFnZQ==",
                    }
                ],
                "recommendations": [
                    {
                        "rank": 0,
                        "style_name": "Soft Down Perm",
                    }
                ],
            }
        }
        output_response.raise_for_status.return_value = None
        mock_get.side_effect = [status_response, output_response]

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_API_KEY": "test-key",
                "RUNPOD_ENDPOINT_ID": "test-endpoint",
                "RUNPOD_BASE_URL": "https://api.runpod.ai/v2",
                "RUNPOD_POLL_INTERVAL_SECONDS": "0.01",
            },
            clear=False,
        ):
            payload = _post_runpod({"action": "simulate"})

        self.assertIsNotNone(payload)
        self.assertEqual(payload["results"][0]["rank"], 0)
        self.assertEqual(payload["recommendations"][0]["style_name"], "Soft Down Perm")
        self.assertEqual(mock_get.call_count, 2)
