from __future__ import annotations

import json
import tarfile
import tempfile
from io import BytesIO
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from app.api.v1.services_django import get_trend_recommendations
from app.models_django import Style
from app.services.trend_refresh import (
    build_chromadb_archive,
    run_local_refresh_trends_pipeline,
    trigger_runpod_trend_refresh,
    trigger_runpod_trend_refresh_with_archive,
)
from app.trend_pipeline.style_collection import sync_seed_styles_to_db


class TrendRefreshServiceTests(SimpleTestCase):
    def test_trigger_runpod_pipeline_uses_runsync_payload_shape(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "id": "sync-job",
            "status": "COMPLETED",
            "output": {"success": True, "steps_completed": ["crawl"]},
        }

        with patch("app.services.trend_refresh.requests.post", return_value=response) as mock_post:
            payload = trigger_runpod_trend_refresh(
                steps=["crawl"],
                endpoint_id="endpoint-123",
                api_key="secret-key",
                sync=True,
            )

        self.assertEqual(payload["request_input"], {"action": "refresh_trends", "steps": ["crawl"]})
        self.assertEqual(payload["runpod_response"]["success"], True)
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"], {"input": {"action": "refresh_trends", "steps": ["crawl"]}})
        self.assertTrue(str(mock_post.call_args.args[0]).endswith("/endpoint-123/runsync"))

    def test_trigger_runpod_pipeline_polls_when_runsync_returns_in_queue(self):
        submit_response = Mock()
        submit_response.raise_for_status.return_value = None
        submit_response.json.return_value = {"id": "sync-job", "status": "IN_QUEUE"}

        completed_response = Mock()
        completed_response.raise_for_status.return_value = None
        completed_response.json.return_value = {
            "id": "sync-job",
            "status": "COMPLETED",
            "output": {"success": True, "steps_completed": ["crawl"]},
        }

        with (
            patch("app.services.trend_refresh.requests.post", return_value=submit_response) as mock_post,
            patch("app.services.trend_refresh.requests.get", return_value=completed_response) as mock_get,
            patch("app.services.trend_refresh.time.sleep", return_value=None),
        ):
            payload = trigger_runpod_trend_refresh(
                steps=["crawl"],
                endpoint_id="endpoint-123",
                api_key="secret-key",
                sync=True,
                timeout=30,
                poll_interval=0.1,
            )

        self.assertEqual(payload["runpod_response"]["success"], True)
        mock_post.assert_called_once()
        mock_get.assert_called_once()

    def test_trigger_runpod_archive_polls_async_job_and_fetches_output_url(self):
        with tempfile.TemporaryDirectory(prefix="mirrai-final-ai-") as tmpdir:
            stores_dir = Path(tmpdir) / "data" / "rag" / "stores"
            for name in ("chromadb_trends", "chromadb_ncs", "chromadb_styles"):
                path = stores_dir / name
                path.mkdir(parents=True, exist_ok=True)
                (path / "marker.txt").write_text(name, encoding="utf-8")

            submit_response = Mock()
            submit_response.raise_for_status.return_value = None
            submit_response.json.return_value = {"id": "job-1", "status": "IN_QUEUE"}

            in_progress_response = Mock()
            in_progress_response.raise_for_status.return_value = None
            in_progress_response.json.return_value = {"id": "job-1", "status": "IN_PROGRESS"}

            completed_response = Mock()
            completed_response.raise_for_status.return_value = None
            completed_response.json.return_value = {
                "id": "job-1",
                "status": "COMPLETED",
                "output_url": "https://example.com/output/job-1",
            }

            output_response = Mock()
            output_response.raise_for_status.return_value = None
            output_response.json.return_value = {"success": True, "mode": "receive_archive"}

            with (
                patch("app.services.trend_refresh.requests.post", return_value=submit_response) as mock_post,
                patch(
                    "app.services.trend_refresh.requests.get",
                    side_effect=[in_progress_response, completed_response, output_response],
                ) as mock_get,
                patch("app.services.trend_refresh.time.sleep", return_value=None),
            ):
                payload = trigger_runpod_trend_refresh_with_archive(
                    endpoint_id="endpoint-123",
                    api_key="secret-key",
                    stores_root=stores_dir,
                    sync=False,
                    wait=True,
                )

        self.assertEqual(payload["archive"]["collections"], ["chromadb_trends", "chromadb_ncs", "chromadb_styles"])
        self.assertEqual(payload["runpod_response"]["success"], True)
        _, kwargs = mock_post.call_args
        encoded_archive = kwargs["json"]["input"]["chromadb_tar_base64"]
        self.assertTrue(encoded_archive)
        self.assertEqual(mock_get.call_count, 3)

    def test_build_chromadb_archive_includes_expected_directories(self):
        with tempfile.TemporaryDirectory(prefix="mirrai-final-ai-") as tmpdir:
            stores_dir = Path(tmpdir) / "data" / "rag" / "stores"
            for name in ("chromadb_trends", "chromadb_ncs"):
                path = stores_dir / name
                path.mkdir(parents=True, exist_ok=True)
                (path / "marker.txt").write_text(name, encoding="utf-8")

            archive_bytes, included = build_chromadb_archive(
                stores_root=stores_dir,
                include_ncs=True,
                include_styles=True,
            )

        self.assertEqual(included, ["chromadb_trends", "chromadb_ncs"])
        with tarfile.open(fileobj=BytesIO(archive_bytes), mode="r:gz") as archive:
            members = archive.getnames()
        self.assertIn("chromadb_trends", members)
        self.assertIn("chromadb_ncs", members)
        self.assertNotIn("chromadb_styles", members)

    def test_trigger_runpod_archive_dry_run_builds_archive_without_http_call(self):
        with tempfile.TemporaryDirectory(prefix="mirrai-final-ai-") as tmpdir:
            stores_root = Path(tmpdir) / "stores"
            chroma_trends = stores_root / "chromadb_trends"
            chroma_trends.mkdir(parents=True, exist_ok=True)
            (chroma_trends / "marker.txt").write_text("ok", encoding="utf-8")

            with patch("app.services.trend_refresh.requests.post") as mock_post:
                payload = trigger_runpod_trend_refresh_with_archive(
                    stores_root=stores_root,
                    dry_run=True,
                )

        self.assertEqual(payload["request_mode"], "runpod_archive")
        self.assertEqual(payload["archive"]["collections"], ["chromadb_trends"])
        self.assertTrue(payload["dry_run"])
        mock_post.assert_not_called()

    def test_run_local_refresh_pipeline_calls_internal_refresh_function(self):
        with patch(
            "app.services.trend_refresh.refresh_trends",
            return_value={
                "success": True,
                "steps_requested": ["crawl", "refine"],
                "steps_completed": ["crawl", "refine"],
                "steps_failed": [],
                "details": {},
            },
        ) as mock_refresh:
            result = run_local_refresh_trends_pipeline(steps=["crawl", "refine"])

        self.assertEqual(result["success"], True)
        self.assertEqual(result["steps_requested"], ["crawl", "refine"])
        mock_refresh.assert_called_once_with(steps=["crawl", "refine"])

    @override_settings(
        RUNPOD_API_KEY="secret-key",
        RUNPOD_TRENDS_ENDPOINT_ID="endpoint-123",
    )
    def test_management_command_prints_json_result(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "id": "sync-job",
            "status": "COMPLETED",
            "output": {"success": True, "mode": "receive_archive"},
        }

        with (
            patch("app.services.trend_refresh.requests.post", return_value=response),
            patch("app.services.trend_refresh.build_chromadb_archive", return_value=(b"abc", ["chromadb_trends"])),
        ):
            out = StringIO()
            call_command(
                "refresh_trends",
                "--mode",
                "runpod-archive",
                stdout=out,
            )
            rendered = out.getvalue()

        parsed = json.loads(rendered)
        self.assertEqual(parsed["request_mode"], "runpod_archive")
        self.assertEqual(parsed["runpod_response"]["success"], True)


class TrendRefreshDatabaseSyncTests(TestCase):
    def test_sync_seed_styles_to_db_creates_or_updates_style_rows(self):
        result = sync_seed_styles_to_db(
            styles=[
                {
                    "style_name": "Soft Wolf Cut",
                    "description": "Layered wolf cut synced from trend seed.",
                    "mood": ["trendy"],
                },
                {
                    "style_name": "Curtain Bob",
                    "description": "Jaw-length bob synced from trend seed.",
                    "mood": ["classic"],
                },
            ]
        )

        self.assertEqual(result["style_count"], 2)
        self.assertEqual(Style.objects.filter(name="Soft Wolf Cut").count(), 1)
        self.assertEqual(Style.objects.get(name="Curtain Bob").vibe, "Classic")
        self.assertEqual(result["duplicate_count"], 0)
        self.assertEqual(result["skipped_count"], 0)

    def test_sync_seed_styles_to_db_skips_blank_names_and_duplicate_names(self):
        result = sync_seed_styles_to_db(
            styles=[
                {
                    "style_name": "Soft Wolf Cut",
                    "description": "First row.",
                    "mood": ["trendy"],
                },
                {
                    "style_name": "Soft Wolf Cut",
                    "description": "Duplicate row should be ignored.",
                    "mood": ["classic"],
                },
                {
                    "style_name": "   ",
                    "description": "Blank names should not create DB rows.",
                    "mood": ["natural"],
                },
            ]
        )

        self.assertEqual(result["style_count"], 1)
        self.assertEqual(result["created_count"], 1)
        self.assertEqual(result["duplicate_count"], 1)
        self.assertEqual(result["skipped_count"], 1)
        self.assertEqual(Style.objects.filter(name="Soft Wolf Cut").count(), 1)

    def test_trend_fallback_prefers_synced_seed_styles(self):
        sync_seed_styles_to_db(
            styles=[
                {
                    "style_name": "Soft Wolf Cut",
                    "description": "Layered wolf cut synced from trend seed.",
                    "keywords": ["wolf cut", "layered"],
                    "mood": ["trendy"],
                    "freshness_score": 0.88,
                    "source": "test_seed",
                    "last_updated": "2026-03-27",
                },
                {
                    "style_name": "Curtain Bob",
                    "description": "Jaw-length bob synced from trend seed.",
                    "keywords": ["bob", "curtain"],
                    "mood": ["classic"],
                    "freshness_score": 0.72,
                    "source": "test_seed",
                    "last_updated": "2026-03-27",
                },
            ]
        )

        with patch(
            "app.api.v1.services_django.load_hairstyles",
            return_value=[
                {
                    "style_name": "Soft Wolf Cut",
                    "description": "Layered wolf cut synced from trend seed.",
                    "keywords": ["wolf cut", "layered"],
                    "freshness_score": 0.88,
                    "source": "test_seed",
                    "last_updated": "2026-03-27",
                },
                {
                    "style_name": "Curtain Bob",
                    "description": "Jaw-length bob synced from trend seed.",
                    "keywords": ["bob", "curtain"],
                    "freshness_score": 0.72,
                    "source": "test_seed",
                    "last_updated": "2026-03-27",
                },
            ],
        ):
            payload = get_trend_recommendations(days=30, client=None)

        self.assertEqual(payload["items"][0]["style_name"], "Soft Wolf Cut")
        self.assertEqual(
            payload["items"][0]["reasoning_snapshot"]["summary"],
            "fallback trend catalog synced from refreshed seed data",
        )
