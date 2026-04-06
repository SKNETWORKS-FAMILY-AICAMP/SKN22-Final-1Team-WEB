from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand
from django.db import connection


from app.models_model_team import LegacyClientAnalysis
from app.services.capture_validation import infer_capture_reason_code


class Command(BaseCommand):
    help = "Summarize capture/upload failure patterns and front-vs-back comparison signals."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Maximum number of latest capture-analysis rows to inspect. Default: 200",
        )

    def handle(self, *args, **options):
        limit = max(int(options["limit"]), 1)
        existing_tables = set(connection.introspection.table_names())
        if LegacyClientAnalysis._meta.db_table not in existing_tables:
            self.stdout.write(self.style.WARNING("client_analysis table is not available in the active database."))
            return

        rows = list(
            LegacyClientAnalysis.objects.order_by("-updated_at_ts", "-analysis_id")[:limit]
        )

        status_counts: Counter[str] = Counter()
        reason_counts: Counter[str] = Counter()
        failed_face_counts: Counter[str] = Counter()
        comparison_counts: Counter[str] = Counter()

        for row in rows:
            status = str(row.status or "UNKNOWN")
            status_counts[status] += 1

            privacy_snapshot = row.privacy_snapshot or {}
            validation_snapshot = {}
            if isinstance(privacy_snapshot, dict):
                validation_snapshot = privacy_snapshot.get("capture_validation") or {}

            reason_code = infer_capture_reason_code(
                error_note=row.error_note,
                privacy_snapshot=privacy_snapshot if isinstance(privacy_snapshot, dict) else None,
            )
            reason_counts[reason_code] += 1

            if status == "NEEDS_RETAKE":
                failed_face_counts[str(row.face_count if row.face_count is not None else "null")] += 1

            if isinstance(validation_snapshot, dict) and validation_snapshot:
                if validation_snapshot.get("front_capture_context_present"):
                    comparison_counts["front_context_present"] += 1
                if validation_snapshot.get("backend_failed_after_front_ready"):
                    comparison_counts["backend_failed_after_front_ready"] += 1

        self.stdout.write(self.style.SUCCESS(f"Capture upload pattern summary (latest {len(rows)} rows)"))
        self.stdout.write("")

        self.stdout.write("Status counts:")
        for key, value in sorted(status_counts.items()):
            self.stdout.write(f"  - {key}: {value}")

        self.stdout.write("")
        self.stdout.write("Reason counts:")
        for key, value in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0])):
            self.stdout.write(f"  - {key}: {value}")

        self.stdout.write("")
        self.stdout.write("Retake face_count distribution:")
        for key, value in sorted(failed_face_counts.items(), key=lambda item: item[0]):
            self.stdout.write(f"  - {key}: {value}")

        self.stdout.write("")
        self.stdout.write("Front-vs-back comparison signals:")
        if comparison_counts:
            for key, value in sorted(comparison_counts.items()):
                self.stdout.write(f"  - {key}: {value}")
        else:
            self.stdout.write("  - none captured yet")
