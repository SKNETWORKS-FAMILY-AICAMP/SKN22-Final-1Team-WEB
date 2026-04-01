from __future__ import annotations

from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase, override_settings

from app.models_django import Style


LEGACY_TABLE_DDL = (
    """
    CREATE TABLE IF NOT EXISTS shop (
        shop_id TEXT PRIMARY KEY,
        login_id TEXT NOT NULL,
        shop_name TEXT NOT NULL,
        biz_number TEXT,
        owner_phone TEXT,
        password TEXT NOT NULL,
        admin_pin TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS designer (
        designer_id TEXT PRIMARY KEY,
        shop_id TEXT NOT NULL,
        designer_name TEXT NOT NULL,
        login_id TEXT NOT NULL,
        password TEXT NOT NULL,
        is_active BOOLEAN NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS client (
        client_id TEXT PRIMARY KEY,
        shop_id TEXT NOT NULL,
        client_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        gender TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS client_survey (
        survey_id INTEGER PRIMARY KEY,
        client_id TEXT NOT NULL,
        hair_length TEXT,
        hair_mood TEXT,
        hair_condition TEXT,
        hair_color TEXT,
        budget TEXT,
        preference_vector TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS client_analysis (
        analysis_id INTEGER PRIMARY KEY,
        client_id TEXT NOT NULL,
        designer_id TEXT NOT NULL,
        original_image_url TEXT,
        face_type TEXT,
        face_ratio_vector TEXT NOT NULL,
        golden_ratio_score REAL,
        landmark_data TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS client_result (
        result_id INTEGER PRIMARY KEY,
        analysis_id INTEGER NOT NULL,
        client_id TEXT NOT NULL,
        selected_hairstyle_id INTEGER,
        selected_image_url TEXT,
        is_confirmed BOOLEAN NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS client_result_detail (
        detail_id INTEGER PRIMARY KEY,
        result_id INTEGER NOT NULL,
        hairstyle_id INTEGER NOT NULL,
        rank INTEGER NOT NULL,
        similarity_score REAL NOT NULL,
        final_score REAL,
        simulated_image_url TEXT,
        recommendation_reason TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS hairstyle (
        hairstyle_id INTEGER PRIMARY KEY,
        chroma_id TEXT NOT NULL,
        style_name TEXT NOT NULL,
        image_url TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
)

LEGACY_TABLES = (
    "client_result_detail",
    "client_result",
    "client_analysis",
    "client_survey",
    "client",
    "designer",
    "shop",
    "hairstyle",
)


@override_settings(SUPABASE_USE_REMOTE_STORAGE=False)
class LegacyModelSyncTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self._create_legacy_tables()

    def tearDown(self):
        self._drop_legacy_tables()

    def _create_legacy_tables(self):
        with connection.cursor() as cursor:
            for ddl in LEGACY_TABLE_DDL:
                cursor.execute(ddl)

    def _drop_legacy_tables(self):
        with connection.cursor() as cursor:
            for table in LEGACY_TABLES:
                cursor.execute(f"DROP TABLE IF EXISTS {table}")

    def _count(self, table: str) -> int:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            return int(cursor.fetchone()[0])

    def _fetch_one(self, sql: str, params: tuple | list = ()):
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def test_seed_command_populates_legacy_model_tables(self):
        call_command("seed_test_accounts")

        self.assertEqual(self._count("shop"), 1)
        self.assertEqual(self._count("designer"), 2)
        self.assertEqual(self._count("client"), 4)
        self.assertEqual(self._count("client_survey"), 4)
        self.assertEqual(self._count("client_analysis"), 3)
        self.assertEqual(self._count("client_result"), 3)
        self.assertEqual(self._count("client_result_detail"), 15)
        self.assertEqual(self._count("hairstyle"), Style.objects.count())

        shop_row = self._fetch_one(
            "SELECT login_id, shop_name, biz_number, owner_phone, admin_pin FROM shop LIMIT 1"
        )
        self.assertEqual(shop_row[0], "01080001000")
        self.assertEqual(shop_row[1], "MirrAI Test Shop")
        self.assertEqual(shop_row[2], "1012345672")
        self.assertEqual(shop_row[3], "01080001000")
        self.assertEqual(shop_row[4], "1000")

        client_row = self._fetch_one(
            "SELECT client_name, phone, gender FROM client WHERE phone = %s",
            ("01090001004",),
        )
        self.assertIsNotNone(client_row)
        self.assertEqual(client_row[1], "01090001004")
        self.assertEqual(client_row[2], "F")

    def test_explicit_sync_command_runs_after_seed(self):
        call_command("seed_test_accounts")
        call_command("sync_legacy_model_tables", strict=True)

        self.assertEqual(self._count("shop"), 1)
        self.assertEqual(self._count("client_result_detail"), 15)
