from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache

from django.db import connection

from app.models_model_team import (
    LegacyClient,
    LegacyClientAnalysis,
    LegacyClientResult,
    LegacyClientResultDetail,
    LegacyClientSurvey,
    LegacyDesigner,
    LegacyHairstyle,
    LegacyShop,
)


LEGACY_NAMESPACE = uuid.UUID("8c72326e-c379-4c8f-a6ef-3dbb29a4a1f1")
LEGACY_TABLES = [
    "client_result_detail",
    "client_result",
    "client_analysis",
    "client_survey",
    "client",
    "designer",
    "shop",
    "hairstyle",
]


@dataclass(frozen=True)
class LegacySyncSummary:
    shop_count: int
    designer_count: int
    client_count: int
    survey_count: int
    analysis_count: int
    result_count: int
    result_detail_count: int
    hairstyle_count: int


@dataclass(frozen=True)
class CanonicalImportSummary:
    shop_count: int
    designer_count: int
    client_count: int
    survey_count: int
    analysis_count: int
    result_count: int
    consultation_count: int
    hairstyle_count: int


def _legacy_uuid(scope: str, pk: int) -> str:
    value = uuid.uuid5(LEGACY_NAMESPACE, f"{scope}:{pk}")
    if connection.vendor == "postgresql":
        return value
    return str(value)


def _legacy_gender(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"m", "male", "man", "남", "남성"}:
        return "M"
    if normalized in {"f", "female", "woman", "여", "여성"}:
        return "F"
    if normalized.startswith("m"):
        return "M"
    if normalized.startswith("f"):
        return "F"
    return "F"


@lru_cache(maxsize=None)
def _table_names() -> frozenset[str]:
    return frozenset(connection.introspection.table_names())


@lru_cache(maxsize=None)
def _existing_legacy_tables() -> tuple[str, ...]:
    existing = _table_names()
    return tuple(table for table in LEGACY_TABLES if table in existing)


def _require_legacy_tables(*, strict: bool) -> None:
    if _existing_legacy_tables():
        return
    message = "No legacy model tables were found."
    if strict:
        raise RuntimeError(message)
    raise RuntimeError(message)


def _legacy_sync_summary() -> LegacySyncSummary:
    return LegacySyncSummary(
        shop_count=LegacyShop.objects.count(),
        designer_count=LegacyDesigner.objects.count(),
        client_count=LegacyClient.objects.count(),
        survey_count=LegacyClientSurvey.objects.count(),
        analysis_count=LegacyClientAnalysis.objects.count(),
        result_count=LegacyClientResult.objects.count(),
        result_detail_count=LegacyClientResultDetail.objects.count(),
        hairstyle_count=LegacyHairstyle.objects.count(),
    )


def sync_legacy_model_tables(*, strict: bool = False) -> LegacySyncSummary:
    _require_legacy_tables(strict=strict)
    return _legacy_sync_summary()


def sync_legacy_model_tables_if_present(*, strict: bool = False) -> LegacySyncSummary | None:
    if not _existing_legacy_tables():
        if strict:
            raise RuntimeError("No legacy model tables were found.")
        return None
    return _legacy_sync_summary()


def import_legacy_model_tables(*, strict: bool = False) -> CanonicalImportSummary:
    _require_legacy_tables(strict=strict)
    return CanonicalImportSummary(
        shop_count=LegacyShop.objects.count(),
        designer_count=LegacyDesigner.objects.count(),
        client_count=LegacyClient.objects.count(),
        survey_count=LegacyClientSurvey.objects.count(),
        analysis_count=LegacyClientAnalysis.objects.count(),
        result_count=LegacyClientResultDetail.objects.count(),
        consultation_count=LegacyClientResult.objects.filter(is_active=True).count(),
        hairstyle_count=LegacyHairstyle.objects.count(),
    )
