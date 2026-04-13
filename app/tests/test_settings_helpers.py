from django.test import SimpleTestCase

from mirrai_project.settings_helpers import build_cache_settings, resolve_active_database_url


class SettingsHelpersTests(SimpleTestCase):
    def test_build_cache_settings_uses_redis_when_url_present(self):
        cache_config = build_cache_settings(redis_url="redis://127.0.0.1:6379/1", timeout=30, key_prefix="mirrai")

        self.assertEqual(cache_config["default"]["BACKEND"], "django.core.cache.backends.redis.RedisCache")
        self.assertEqual(cache_config["default"]["LOCATION"], "redis://127.0.0.1:6379/1")

    def test_build_cache_settings_falls_back_to_locmem_without_redis(self):
        cache_config = build_cache_settings(redis_url="", timeout=30, key_prefix="mirrai")

        self.assertEqual(cache_config["default"]["BACKEND"], "django.core.cache.backends.locmem.LocMemCache")

    def test_resolve_active_database_url_prefers_remote_then_local_then_database_url(self):
        self.assertEqual(
            resolve_active_database_url(
                supabase_use_remote_db=True,
                supabase_db_url="postgresql://remote",
                local_database_url="sqlite:///db.sqlite3",
                database_url="postgresql://legacy",
            ),
            "postgresql://remote",
        )
        self.assertEqual(
            resolve_active_database_url(
                supabase_use_remote_db=False,
                supabase_db_url="postgresql://remote",
                local_database_url="sqlite:///db.sqlite3",
                database_url="postgresql://legacy",
            ),
            "sqlite:///db.sqlite3",
        )
