from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from app.services.ncs_pdf_runtime_sync import sync_ncs_source_pdfs


class Command(BaseCommand):
    help = "Copy external NCS source PDFs into the runtime directory used by the chatbot."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-dir",
            required=True,
            help="Directory that already contains the NCS PDF files.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Overwrite same-name PDFs already present in the runtime target directory.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with a non-zero code when the sync cannot be completed.",
        )

    def handle(self, *args, **options):
        payload = sync_ncs_source_pdfs(
            source_dir=options["source_dir"],
            overwrite=options["overwrite"],
        )
        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))

        if options["strict"] and not payload.get("success", False):
            reason = payload.get("reason") or payload.get("status") or "unknown"
            raise CommandError(f"NCS PDF sync failed: {reason}")
