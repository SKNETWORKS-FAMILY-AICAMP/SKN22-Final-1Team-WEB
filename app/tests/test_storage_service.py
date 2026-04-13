from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from app.services import storage_service


class StorageReferenceResolutionTests(SimpleTestCase):
    @override_settings(
        SUPABASE_USE_REMOTE_STORAGE=True,
        SUPABASE_BUCKET_PUBLIC=False,
        SUPABASE_SIGNED_URL_EXPIRES_IN=3600,
    )
    @patch("app.services.storage_service.get_supabase_client")
    def test_resolve_storage_reference_uses_style_placeholder_for_missing_style_asset(self, mock_get_supabase_client):
        bucket = Mock()
        bucket.create_signed_url.side_effect = Exception("Object not found")
        client = Mock()
        client.storage.from_.return_value = bucket
        mock_get_supabase_client.return_value = client

        resolved = storage_service.resolve_storage_reference("styles/204.jpg")

        self.assertTrue(str(resolved).startswith("data:image/svg+xml"))

    @override_settings(
        SUPABASE_USE_REMOTE_STORAGE=True,
        SUPABASE_BUCKET_PUBLIC=False,
        SUPABASE_SIGNED_URL_EXPIRES_IN=3600,
    )
    @patch("app.services.storage_service.get_supabase_client")
    def test_resolve_storage_reference_with_status_marks_style_placeholder(self, mock_get_supabase_client):
        bucket = Mock()
        bucket.create_signed_url.side_effect = Exception("Object not found")
        client = Mock()
        client.storage.from_.return_value = bucket
        mock_get_supabase_client.return_value = client

        resolved, status = storage_service._resolve_storage_reference_with_status("styles/206.jpg")

        self.assertTrue(str(resolved).startswith("data:image/svg+xml"))
        self.assertEqual(status, "style_placeholder")

    @override_settings(
        SUPABASE_USE_REMOTE_STORAGE=True,
        SUPABASE_BUCKET_PUBLIC=False,
        SUPABASE_SIGNED_URL_EXPIRES_IN=3600,
    )
    @patch("app.services.storage_service.get_supabase_client")
    def test_resolve_storage_reference_keeps_warning_path_for_non_style_assets(self, mock_get_supabase_client):
        bucket = Mock()
        bucket.create_signed_url.side_effect = Exception("Object not found")
        client = Mock()
        client.storage.from_.return_value = bucket
        mock_get_supabase_client.return_value = client

        resolved = storage_service.resolve_storage_reference("simulations/missing.png")

        self.assertIsNone(resolved)
