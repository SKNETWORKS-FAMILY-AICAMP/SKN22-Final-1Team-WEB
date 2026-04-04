from __future__ import annotations

import logging
import mimetypes
import uuid
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from storage3.types import CreateOrUpdateBucketOptions

from app.services.supabase_client import get_supabase_client


logger = logging.getLogger(__name__)


def _guess_mime(filename: str, default: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or default


def _extract_signed_url(signed) -> str | None:
    if isinstance(signed, dict):
        return signed.get("signedURL") or signed.get("signedUrl")
    return getattr(signed, "signedURL", None) or getattr(signed, "signedUrl", None)


@lru_cache(maxsize=1)
def ensure_supabase_bucket() -> bool:
    if not settings.SUPABASE_USE_REMOTE_STORAGE:
        return False

    client = get_supabase_client()
    if client is None:
        return False

    options = CreateOrUpdateBucketOptions(
        public=settings.SUPABASE_BUCKET_PUBLIC,
        file_size_limit=settings.SUPABASE_BUCKET_FILE_SIZE_LIMIT,
        allowed_mime_types=settings.SUPABASE_ALLOWED_MIME_TYPES,
    )
    try:
        client.storage.get_bucket(settings.SUPABASE_BUCKET)
        client.storage.update_bucket(settings.SUPABASE_BUCKET, options)
    except Exception:
        client.storage.create_bucket(settings.SUPABASE_BUCKET, options=options)
    return True


def _store_locally(
    *,
    original_name: str,
    original_bytes: bytes,
    processed_bytes: bytes,
    original_ext: str,
    deidentified_bytes: bytes | None = None,
) -> tuple[str, str, str, str | None]:
    filename_root = str(uuid.uuid4())
    original_filename = f"{filename_root}{original_ext}"
    processed_filename = f"{filename_root}.processed.jpg"
    deidentified_filename = f"{filename_root}.deidentified.jpg"

    capture_dir = Path(settings.MEDIA_ROOT) / "captures"
    capture_dir.mkdir(parents=True, exist_ok=True)

    original_path = capture_dir / original_filename
    processed_path = capture_dir / processed_filename
    original_path.write_bytes(original_bytes)
    processed_path.write_bytes(processed_bytes)
    deidentified_path = None
    if deidentified_bytes:
        deidentified_path = capture_dir / deidentified_filename
        deidentified_path.write_bytes(deidentified_bytes)

    return original_filename, str(original_path), str(processed_path), (str(deidentified_path) if deidentified_path else None)


def _store_in_supabase(
    *,
    original_name: str,
    original_bytes: bytes,
    processed_bytes: bytes,
    original_ext: str,
    deidentified_bytes: bytes | None = None,
) -> tuple[str, str, str, str | None] | None:
    if not settings.SUPABASE_USE_REMOTE_STORAGE:
        return None

    client = get_supabase_client()
    if client is None:
        return None
    ensure_supabase_bucket()

    filename_root = str(uuid.uuid4())
    original_filename = f"{filename_root}{original_ext}"
    processed_filename = f"{filename_root}.processed.jpg"
    deidentified_filename = f"{filename_root}.deidentified.jpg"
    original_key = f"captures/{original_filename}"
    processed_key = f"captures/{processed_filename}"
    deidentified_key = f"captures/{deidentified_filename}"

    bucket = client.storage.from_(settings.SUPABASE_BUCKET)
    logger.info(
        "[storage] uploading capture assets to bucket=%s original=%s processed=%s deidentified=%s",
        settings.SUPABASE_BUCKET,
        original_key,
        processed_key,
        deidentified_key if deidentified_bytes else None,
    )
    bucket.upload(
        original_key,
        original_bytes,
        file_options={"content-type": _guess_mime(original_name, "application/octet-stream")},
    )
    bucket.upload(
        processed_key,
        processed_bytes,
        file_options={"content-type": "image/jpeg"},
    )
    stored_deidentified_key = None
    if deidentified_bytes:
        bucket.upload(
            deidentified_key,
            deidentified_bytes,
            file_options={"content-type": "image/jpeg"},
        )
        stored_deidentified_key = deidentified_key
    logger.info(
        "[storage] capture assets uploaded bucket=%s original=%s processed=%s deidentified=%s",
        settings.SUPABASE_BUCKET,
        original_key,
        processed_key,
        stored_deidentified_key,
    )
    return original_filename, original_key, processed_key, stored_deidentified_key


def resolve_storage_reference(reference: str | None) -> str | None:
    if not reference:
        return reference

    if reference.startswith(("http://", "https://", "/")):
        return reference

    if not settings.SUPABASE_USE_REMOTE_STORAGE:
        return reference

    client = get_supabase_client()
    if client is None:
        return reference

    bucket = client.storage.from_(settings.SUPABASE_BUCKET)
    if settings.SUPABASE_BUCKET_PUBLIC:
        return bucket.get_public_url(reference)

    try:
        signed = bucket.create_signed_url(reference, settings.SUPABASE_SIGNED_URL_EXPIRES_IN)
    except Exception as exc:
        logger.warning("[storage] unable to resolve signed url for reference=%s: %s", reference, exc)
        return reference
    return _extract_signed_url(signed) or reference


def _resolve_storage_reference_with_status(reference: str | None) -> tuple[str | None, str]:
    if not reference:
        return reference, "missing_reference"

    if reference.startswith(("http://", "https://", "/")):
        return reference, "already_resolved"

    if not settings.SUPABASE_USE_REMOTE_STORAGE:
        return reference, "local_reference"

    client = get_supabase_client()
    if client is None:
        return reference, "storage_client_unavailable"

    bucket = client.storage.from_(settings.SUPABASE_BUCKET)
    if settings.SUPABASE_BUCKET_PUBLIC:
        return bucket.get_public_url(reference), "public_url"

    try:
        signed = bucket.create_signed_url(reference, settings.SUPABASE_SIGNED_URL_EXPIRES_IN)
    except Exception as exc:
        logger.warning("[storage] unable to resolve signed url for reference=%s: %s", reference, exc)
        return reference, "signed_url_failed"

    resolved = _extract_signed_url(signed)
    if resolved:
        return resolved, "signed_url"
    return reference, "signed_url_unresolved"


def build_storage_snapshot(
    *,
    original_path: str | None = None,
    processed_path: str | None = None,
    deidentified_path: str | None = None,
) -> dict:
    paths = {
        "original_path": original_path,
        "processed_path": processed_path,
        "deidentified_path": deidentified_path,
    }
    resolved_pairs = {
        key: _resolve_storage_reference_with_status(value) for key, value in paths.items()
    }
    resolved_urls = {key: pair[0] for key, pair in resolved_pairs.items()}
    resolution_statuses = {key: pair[1] for key, pair in resolved_pairs.items()}
    reference_presence = {key: bool(value) for key, value in paths.items()}
    return {
        "storage_mode": "remote" if settings.SUPABASE_USE_REMOTE_STORAGE else "local",
        "bucket_name": settings.SUPABASE_BUCKET,
        "bucket_public": settings.SUPABASE_BUCKET_PUBLIC,
        "remote_storage_enabled": settings.SUPABASE_USE_REMOTE_STORAGE,
        "paths": paths,
        "resolved_urls": resolved_urls,
        "resolution_statuses": resolution_statuses,
        "reference_presence": reference_presence,
        "path_count": sum(1 for value in paths.values() if value),
        "resolved_url_count": sum(1 for value in resolved_urls.values() if value),
        "has_original": bool(original_path),
        "has_processed": bool(processed_path),
        "has_deidentified": bool(deidentified_path),
        "has_required_capture_assets": bool(original_path and processed_path),
        "fully_resolved_capture_assets": bool(
            original_path
            and processed_path
            and resolved_urls.get("original_path")
            and resolved_urls.get("processed_path")
        ),
    }


def store_capture_assets(
    *,
    original_name: str,
    original_bytes: bytes,
    processed_bytes: bytes,
    original_ext: str,
    deidentified_bytes: bytes | None = None,
) -> tuple[str, str, str, str | None]:
    remote_result = _store_in_supabase(
        original_name=original_name,
        original_bytes=original_bytes,
        processed_bytes=processed_bytes,
        original_ext=original_ext,
        deidentified_bytes=deidentified_bytes,
    )
    if remote_result:
        return remote_result
    return _store_locally(
        original_name=original_name,
        original_bytes=original_bytes,
        processed_bytes=processed_bytes,
        original_ext=original_ext,
        deidentified_bytes=deidentified_bytes,
    )
