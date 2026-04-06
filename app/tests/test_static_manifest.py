import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


class VerifyStaticManifestCommandTests(SimpleTestCase):
    def test_verify_static_manifest_requires_manifest_file(self):
        with TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "staticfiles.json"
            with self.assertRaisesMessage(CommandError, "Staticfiles manifest not found"):
                call_command("verify_static_manifest", manifest_path=str(missing_path))

    def test_verify_static_manifest_requires_expected_entry(self):
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "staticfiles.json"
            manifest_path.write_text(json.dumps({"paths": {"other.css": "other.123.css"}}), encoding="utf-8")

            with self.assertRaisesMessage(CommandError, "shared/styles/base.css"):
                call_command("verify_static_manifest", manifest_path=str(manifest_path))

    def test_verify_static_manifest_passes_with_required_entry(self):
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "staticfiles.json"
            manifest_path.write_text(
                json.dumps({"paths": {"shared/styles/base.css": "shared/styles/base.123.css"}}),
                encoding="utf-8",
            )
            stdout = StringIO()

            call_command("verify_static_manifest", manifest_path=str(manifest_path), stdout=stdout)

            self.assertIn("Staticfiles manifest verified", stdout.getvalue())
