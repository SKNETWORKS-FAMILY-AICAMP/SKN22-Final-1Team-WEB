from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, override_settings

from app.services import storage_service


class StorageServiceTests(SimpleTestCase):
    def test_resolve_storage_reference_preserves_trimmed_data_url(self):
        reference = "  data:image/webp;base64,ZmFrZQ==  "

        resolved = storage_service.resolve_storage_reference(reference)

        self.assertEqual(resolved, "data:image/webp;base64,ZmFrZQ==")

    def test_persist_simulation_image_reference_keeps_jpeg_data_url_as_jpg_asset(self):
        with TemporaryDirectory() as temp_dir:
            with override_settings(
                MEDIA_ROOT=temp_dir,
                MEDIA_URL="/media/",
                SUPABASE_USE_REMOTE_STORAGE=False,
            ):
                persisted = storage_service.persist_simulation_image_reference(
                    "data:image/jpeg;base64,ZmFrZQ=="
                )

                self.assertIsNotNone(persisted)
                self.assertTrue(str(persisted).startswith("/media/simulations/"))
                self.assertTrue(str(persisted).endswith(".jpg"))

                relative_path = str(persisted).removeprefix("/media/")
                stored_file = Path(temp_dir) / relative_path
                self.assertTrue(stored_file.exists())
                self.assertEqual(stored_file.read_bytes(), b"fake")
                self.assertEqual(
                    storage_service.load_storage_reference_bytes(str(persisted)),
                    b"fake",
                )
