from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from app.api.v1 import admin_services
from app.services.runtime_cache import invalidate_partner_client_cache


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "partner-runtime-cache-tests",
        }
    },
    REDIS_KEY_PREFIX="test-mirrai",
    PARTNER_DASHBOARD_CACHE_SECONDS=30,
    PARTNER_REPORT_CACHE_SECONDS=90,
)
class PartnerRuntimeCacheTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.admin = SimpleNamespace(id=101)

    def test_dashboard_summary_uses_cache_for_same_scope(self):
        selection_row = {
            "style_id": 7,
            "style_name": "Soft Layer",
            "image_url": "/media/style-7.jpg",
            "client_id": 1,
            "legacy_client_id": "legacy-1",
        }
        active_row = {
            "client_id": 1,
            "legacy_client_id": "legacy-1",
            "has_unread_consultation": False,
        }

        with (
            patch.object(admin_services, "ensure_catalog_styles", return_value={}) as ensure_catalog_styles,
            patch.object(admin_services, "get_legacy_confirmed_selection_items", return_value=[selection_row]) as confirmed_items,
            patch.object(admin_services, "get_style_record", return_value=None),
            patch.object(admin_services, "resolve_storage_reference", side_effect=lambda value: value),
            patch.object(admin_services, "get_legacy_active_consultation_items", return_value=[active_row]),
            patch.object(admin_services, "_serialize_consultation_like", return_value={"client_id": 1}),
            patch.object(admin_services, "_ai_health", return_value={"status": "online"}),
        ):
            first = admin_services.get_admin_dashboard_summary(admin=self.admin)
            second = admin_services.get_admin_dashboard_summary(admin=self.admin)

        self.assertEqual(first, second)
        self.assertEqual(ensure_catalog_styles.call_count, 1)
        self.assertEqual(confirmed_items.call_count, 1)

    def test_active_client_sessions_uses_cache_for_same_scope(self):
        active_row = {
            "client_id": 1,
            "legacy_client_id": "legacy-1",
            "has_unread_consultation": False,
        }

        with (
            patch.object(admin_services, "get_legacy_active_consultation_items", return_value=[active_row]) as active_items,
            patch.object(admin_services, "_serialize_consultation_like", return_value={"client_id": 1}),
        ):
            first = admin_services.get_active_client_sessions(admin=self.admin)
            second = admin_services.get_active_client_sessions(admin=self.admin)

        self.assertEqual(first, second)
        self.assertEqual(active_items.call_count, 1)

    def test_trend_report_cache_is_invalidated_by_scope_version_bump(self):
        selection_row = {
            "style_id": 7,
            "style_name": "Soft Layer",
            "image_url": "/media/style-7.jpg",
            "keywords": ["soft"],
            "client_id": 1,
            "legacy_client_id": "legacy-1",
            "survey_snapshot": {"target_length": "medium"},
            "age_profile": {"age_decade": "20s", "age_group": "young_adult"},
        }

        client = SimpleNamespace(id=1)
        with (
            patch.object(admin_services, "get_legacy_confirmed_selection_items", return_value=[selection_row]) as confirmed_items,
            patch.object(
                admin_services,
                "_style_snapshot",
                return_value={"style_id": 7, "style_name": "Soft Layer", "image_url": "/media/style-7.jpg", "keywords": ["soft"]},
            ),
            patch.object(admin_services, "get_legacy_active_consultation_items", return_value=[]),
            patch.object(admin_services, "resolve_storage_reference", side_effect=lambda value: value),
        ):
            first = admin_services.get_admin_trend_report(
                days=7,
                filters={"target_length": "medium"},
                admin=self.admin,
            )
            second = admin_services.get_admin_trend_report(
                days=7,
                filters={"target_length": "medium"},
                admin=self.admin,
            )
            invalidate_partner_client_cache(client=client, admin=self.admin)
            third = admin_services.get_admin_trend_report(
                days=7,
                filters={"target_length": "medium"},
                admin=self.admin,
            )

        self.assertEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual(confirmed_items.call_count, 2)

    def test_style_report_uses_cache_for_same_scope(self):
        profile_a = SimpleNamespace(style_id=7, keywords=["soft", "layer"], vibe_tags=["clean"])
        profile_b = SimpleNamespace(style_id=8, keywords=["soft"], vibe_tags=["clean"])
        selection_row = {"style_id": 7}

        with (
            patch.object(admin_services, "_style_snapshot", return_value={"style_id": 7, "style_name": "Soft Layer"}) as style_snapshot,
            patch.object(admin_services, "get_legacy_confirmed_selection_items", return_value=[selection_row]) as confirmed_items,
            patch.object(admin_services, "STYLE_CATALOG", [profile_a, profile_b]),
        ):
            first = admin_services.get_style_report(style_id=7, days=7, admin=self.admin)
            second = admin_services.get_style_report(style_id=7, days=7, admin=self.admin)

        self.assertEqual(first, second)
        self.assertEqual(confirmed_items.call_count, 1)
        self.assertEqual(style_snapshot.call_count, 2)
