from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from app.services.trend_refresh import (
    TrendRefreshError,
    trigger_local_trend_refresh,
    trigger_runpod_trend_refresh,
    trigger_runpod_trend_refresh_with_archive,
)


class Command(BaseCommand):
    help = "Refresh trend data locally or through optional RunPod helper modes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--mode",
            choices=("local", "runpod-pipeline", "runpod-archive"),
            default="local",
            help="local runs the backend trend pipeline. RunPod modes are optional compatibility helpers.",
        )
        parser.add_argument(
            "--steps",
            default="",
            help="Comma-separated refresh steps. Used for pipeline mode and for optional local builds in archive mode.",
        )
        parser.add_argument(
            "--async",
            dest="use_async",
            action="store_true",
            help="Use /run and poll the job instead of /runsync.",
        )
        parser.add_argument(
            "--no-wait",
            action="store_true",
            help="Submit an async job and return immediately. Ignored for sync mode.",
        )
        parser.add_argument("--timeout", type=int, default=1800, help="Sync request timeout or async poll timeout in seconds.")
        parser.add_argument("--poll-interval", type=float, default=5.0, help="Async poll interval in seconds.")
        parser.add_argument("--endpoint-id", default="", help="Override RUNPOD_TRENDS_ENDPOINT_ID.")
        parser.add_argument("--api-key", default="", help="Override RUNPOD_API_KEY.")
        parser.add_argument("--base-url", default="", help="Override RUNPOD_BASE_URL.")
        parser.add_argument("--dry-run", action="store_true", help="Build the payload locally and skip the RunPod HTTP call.")
        parser.add_argument(
            "--build-local",
            action="store_true",
            help="In archive mode, run the internal backend trend pipeline before creating the tar.gz.",
        )
        parser.add_argument("--skip-ncs", action="store_true", help="Exclude chromadb_ncs from the uploaded archive.")
        parser.add_argument("--skip-styles", action="store_true", help="Exclude chromadb_styles from the uploaded archive.")

    def handle(self, *args, **options):
        try:
            sync = not options["use_async"]
            wait = sync or not options["no_wait"]

            if options["mode"] == "local":
                payload = trigger_local_trend_refresh(
                    steps=options["steps"] or None,
                    dry_run=options["dry_run"],
                )
            elif options["mode"] == "runpod-archive":
                payload = trigger_runpod_trend_refresh_with_archive(
                    endpoint_id=options["endpoint_id"] or None,
                    api_key=options["api_key"] or None,
                    base_url=options["base_url"] or None,
                    sync=sync,
                    wait=wait,
                    timeout=options["timeout"],
                    poll_interval=options["poll_interval"],
                    build_locally=options["build_local"],
                    steps=options["steps"] or None,
                    include_ncs=not options["skip_ncs"],
                    include_styles=not options["skip_styles"],
                    dry_run=options["dry_run"],
                )
            else:
                payload = trigger_runpod_trend_refresh(
                    steps=options["steps"] or None,
                    endpoint_id=options["endpoint_id"] or None,
                    api_key=options["api_key"] or None,
                    base_url=options["base_url"] or None,
                    sync=sync,
                    wait=wait,
                    timeout=options["timeout"],
                    poll_interval=options["poll_interval"],
                    dry_run=options["dry_run"],
                )
        except TrendRefreshError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))

        if wait and not options["dry_run"]:
            runpod_response = payload.get("runpod_response", {})
            if isinstance(runpod_response, dict) and runpod_response.get("success") is False:
                raise CommandError("Trend refresh completed but RunPod reported success=false.")
