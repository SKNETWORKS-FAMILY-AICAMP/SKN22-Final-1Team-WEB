import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verify that collectstatic produced a manifest with required static entries."

    def add_arguments(self, parser):
        parser.add_argument(
            "--manifest-path",
            default=None,
            help="Optional override for the manifest file path.",
        )
        parser.add_argument(
            "--require",
            action="append",
            default=[],
            help="Static path that must exist in the manifest. Can be passed multiple times.",
        )

    def handle(self, *args, **options):
        manifest_override = options["manifest_path"]
        manifest_path = Path(manifest_override) if manifest_override else Path(settings.STATIC_ROOT) / "staticfiles.json"

        if not manifest_path.exists():
            raise CommandError(f"Staticfiles manifest not found: {manifest_path}")

        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Staticfiles manifest is not valid JSON: {exc}") from exc

        paths = payload.get("paths") or {}
        required = options["require"] or ["shared/styles/base.css"]
        missing = [entry for entry in required if entry not in paths]

        if missing:
            raise CommandError(
                "Staticfiles manifest is missing required entries: " + ", ".join(sorted(missing))
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Staticfiles manifest verified: {manifest_path} ({len(required)} required entries present)"
            )
        )
