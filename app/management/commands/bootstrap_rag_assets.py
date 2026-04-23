from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from app.services.rag_bootstrap import bootstrap_rag_assets


class Command(BaseCommand):
    help = "Ensure packaged RAG JSON/Chroma assets are available inside the running container."

    def add_arguments(self, parser):
        parser.add_argument("--skip-trends", action="store_true", help="Skip trend store bootstrap.")
        parser.add_argument("--skip-ncs", action="store_true", help="Skip NCS store bootstrap.")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with a non-zero code if any required packaged asset is missing.",
        )

    def handle(self, *args, **options):
        payload = bootstrap_rag_assets(
            include_trends=not options["skip_trends"],
            include_ncs=not options["skip_ncs"],
        )
        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))

        if options["strict"] and not payload.get("success", False):
            missing = ", ".join(payload.get("missing_inputs", [])) or "unknown"
            raise CommandError(f"RAG asset bootstrap did not complete successfully. Missing: {missing}")
