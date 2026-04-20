from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

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

    def test_persist_named_asset_reference_skips_put_object_when_s3_bucket_unavailable(self):
        with TemporaryDirectory() as temp_dir:
            with override_settings(
                MEDIA_ROOT=temp_dir,
                MEDIA_URL="/media/",
                SUPABASE_USE_REMOTE_STORAGE=False,
                S3_BUCKET_NAME="missing-demo-bucket",
            ):
                storage_service._s3_bucket_is_accessible.cache_clear()
                client = Mock()
                client.head_bucket.side_effect = ValueError("NoSuchBucket")

                with patch.object(storage_service, "_get_s3_client", return_value=client):
                    persisted = storage_service.persist_named_asset_reference(
                        b"fake",
                        relative_path="chatbot/ncs/sample/img-01.png",
                        mime_type="image/png",
                    )

                self.assertIsNotNone(persisted)
                self.assertTrue(str(persisted).startswith("/media/chatbot/ncs/sample/"))
                client.put_object.assert_not_called()
                storage_service._s3_bucket_is_accessible.cache_clear()

    def test_persist_named_asset_reference_uses_supabase_before_local_when_s3_is_unavailable(self):
        with TemporaryDirectory() as temp_dir:
            with override_settings(
                MEDIA_ROOT=temp_dir,
                MEDIA_URL="/media/",
                SUPABASE_USE_REMOTE_STORAGE=True,
            ):
                with patch.object(storage_service, "_store_generated_asset_in_s3", return_value=None), patch.object(
                    storage_service,
                    "_store_generated_asset_in_supabase",
                    return_value="chatbot/ncs/remote-image.png",
                ):
                    persisted = storage_service.persist_named_asset_reference(
                        b"fake",
                        relative_path="chatbot/ncs/sample/img-01.png",
                        mime_type="image/png",
                    )

                self.assertEqual(persisted, "chatbot/ncs/remote-image.png")
                local_file = Path(temp_dir) / "chatbot" / "ncs" / "sample" / "img-01.png"
                self.assertFalse(local_file.exists())
