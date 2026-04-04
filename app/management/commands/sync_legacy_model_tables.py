from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from app.services.legacy_model_sync import sync_legacy_model_tables


class Command(BaseCommand):
    help = "Synchronize canonical backend tables into legacy model-team tables."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail if any expected legacy table is missing.",
        )

    def handle(self, *args, **options):
        strict = bool(options["strict"])

        try:
            summary = sync_legacy_model_tables(strict=strict)
        except RuntimeError as exc:
            message = str(exc)
            if "No legacy model tables were found." in message and not strict:
                self.stdout.write(self.style.WARNING(message))
                return
            raise CommandError(message) from exc

        self.stdout.write(self.style.SUCCESS("Legacy model tables have been synchronized."))
        self.stdout.write(
            "summary: "
            f"shop={summary.shop_count}, "
            f"designer={summary.designer_count}, "
            f"client={summary.client_count}, "
            f"survey={summary.survey_count}, "
            f"analysis={summary.analysis_count}, "
            f"result={summary.result_count}, "
            f"result_detail={summary.result_detail_count}, "
            f"hairstyle={summary.hairstyle_count}"
        )
