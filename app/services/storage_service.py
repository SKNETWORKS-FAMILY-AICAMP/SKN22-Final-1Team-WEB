from __future__ import annotations

import base64
import logging
import mimetypes
import uuid
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from storage3.types import CreateOrUpdateBucketOptions

from app.services.supabase_client import get_supabase_client


logger = logging.getLogger(__name__)

STYLE_REFERENCE_PREFIXES = ("styles/", "/media/styles/")


def _guess_mime(filename: str, default: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or default


def _is_style_reference(reference: str | None) -> bool:
    text = str(reference or "").strip()
    return text.startswith(STYLE_REFERENCE_PREFIXES)


def _escape_svg_text(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _style_placeholder_reference(reference: str | None) -> str:
    label = Path(str(reference or "style")).stem.replace("-", " ").replace("_", " ").strip() or "Style"
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 600">'
        '<defs>'
        '<linearGradient id="g" x1="0" x2="1" y1="0" y2="1">'
        '<stop offset="0%" stop-color="#f7f7f7" />'
        '<stop offset="100%" stop-color="#ececec" />'
        "</linearGradient>"
        "</defs>"
        '<rect width="480" height="600" rx="28" fill="url(#g)" />'
        '<circle cx="240" cy="220" r="92" fill="#111111" opacity="0.08" />'
        '<path d="M160 348c24-44 69-66 136-66s112 22 136 66v72H160z" fill="#111111" opacity="0.06" />'
        '<text x="240" y="458" text-anchor="middle" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#111111">Style Preview</text>'
        f'<text x="240" y="492" text-anchor="middle" font-family="Arial, sans-serif" font-size="18" fill="#555555">{_escape_svg_text(label)}</text>'
        "</svg>"
    )
    return "data:image/svg+xml;charset=UTF-8," + quote(svg)


def _style_placeholder_if_missing(reference: str | None) -> str | None:
    normalized_reference = str(reference or "").strip()
    if not _is_style_reference(normalized_reference):
        return None
    if normalized_reference.startswith("/media/") and _resolve_local_asset_path(normalized_reference) is not None:
        return None
    return _style_placeholder_reference(normalized_reference)


def _decode_data_image_reference(reference: str) -> tuple[bytes, str, str] | None:
    normalized_reference = str(reference or "").strip()
    if not normalized_reference.startswith("data:image/") or "," not in normalized_reference:
        return None

    header, _, encoded = normalized_reference.partition(",")
    if ";base64" not in header:
        return None

    mime_type = header[5:].split(";", 1)[0].strip() or "application/octet-stream"
    extension = mimetypes.guess_extension(mime_type) or ".bin"
    if extension == ".jpe":
        extension = ".jpg"

    return base64.b64decode(encoded), mime_type, extension


def _resolve_local_asset_path(reference: str) -> Path | None:
    text = str(reference or "").strip()
    if not text:
        return None

    media_prefix = str(settings.MEDIA_URL or "/media/")
    if media_prefix and text.startswith(media_prefix):
        relative = text[len(media_prefix):].lstrip("/\\")
        candidate = Path(settings.MEDIA_ROOT) / relative
        if candidate.exists():
            return candidate

    candidate = Path(text)
    if candidate.exists():
        return candidate

    return None


def _store_generated_asset_locally(*, asset_bytes: bytes, extension: str, subdir: str) -> str:
    filename = f"{uuid.uuid4()}{extension}"
    asset_dir = Path(settings.MEDIA_ROOT) / subdir
    asset_dir.mkdir(parents=True, exist_ok=True)
    stored_path = asset_dir / filename
    stored_path.write_bytes(asset_bytes)
    return f"{settings.MEDIA_URL.rstrip('/')}/{subdir}/{filename}"


def _store_generated_asset_in_supabase(*, asset_bytes: bytes, extension: str, subdir: str, mime_type: str) -> str | None:
    if not settings.SUPABASE_USE_REMOTE_STORAGE:
        return None

    client = get_supabase_client()
    if client is None:
        return None

    try:
        ensure_supabase_bucket()
    except Exception as exc:
        logger.warning("[storage] Supabase 버킷 준비 실패, 로컬 저장으로 전환합니다: %s", exc)
        return None

    key = f"{subdir}/{uuid.uuid4()}{extension}"
    bucket = client.storage.from_(settings.SUPABASE_BUCKET)
    try:
        bucket.upload(
            key,
            asset_bytes,
            file_options={"content-type": mime_type},
        )
    except Exception as exc:
        logger.warning("[storage] Supabase 업로드 실패 (key=%s): %s", key, exc)
        return None
    return key


def persist_simulation_image_reference(reference: str | None, *, subdir: str = "simulations") -> str | None:
    if not reference:
        return reference

    normalized_reference = str(reference).strip()
    decoded = _decode_data_image_reference(normalized_reference)
    if decoded is None:
        local_asset_path = _resolve_local_asset_path(normalized_reference)
        if local_asset_path is None:
            return normalized_reference

        try:
            asset_bytes = local_asset_path.read_bytes()
        except OSError:
            return normalized_reference

        mime_type = _guess_mime(local_asset_path.name, "application/octet-stream")
        extension = local_asset_path.suffix or mimetypes.guess_extension(mime_type) or ".bin"
        if extension == ".jpe":
            extension = ".jpg"

        remote_reference = _store_generated_asset_in_supabase(
            asset_bytes=asset_bytes,
            extension=extension,
            subdir=subdir,
            mime_type=mime_type,
        )
        if remote_reference:
            return remote_reference

        return _store_generated_asset_locally(
            asset_bytes=asset_bytes,
            extension=extension,
            subdir=subdir,
        )

    asset_bytes, mime_type, extension = decoded
    remote_reference = _store_generated_asset_in_supabase(
        asset_bytes=asset_bytes,
        extension=extension,
        subdir=subdir,
        mime_type=mime_type,
    )
    if remote_reference:
        return remote_reference

    return _store_generated_asset_locally(
        asset_bytes=asset_bytes,
        extension=extension,
        subdir=subdir,
    )


def persist_analysis_input_image_reference(
    asset_bytes: bytes | None,
    *,
    extension: str = ".jpg",
    mime_type: str = "image/jpeg",
    subdir: str = "analysis-inputs",
) -> str | None:
    if not asset_bytes:
        return None

    remote_reference = _store_generated_asset_in_supabase(
        asset_bytes=asset_bytes,
        extension=extension,
        subdir=subdir,
        mime_type=mime_type,
    )
    if remote_reference:
        return remote_reference

    return _store_generated_asset_locally(
        asset_bytes=asset_bytes,
        extension=extension,
        subdir=subdir,
    )


def load_storage_reference_bytes(reference: str | None) -> bytes | None:
    normalized_reference = str(reference or "").strip()
    if not normalized_reference:
        return None

    decoded = _decode_data_image_reference(normalized_reference)
    if decoded is not None:
        asset_bytes, _, _ = decoded
        return asset_bytes

    local_asset_path = _resolve_local_asset_path(normalized_reference)
    if local_asset_path is None:
        return None

    try:
        return local_asset_path.read_bytes()
    except OSError:
        return None


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

    normalized_reference = str(reference).strip()
    if normalized_reference.startswith("data:image/"):
        return normalized_reference

    style_placeholder = _style_placeholder_if_missing(normalized_reference)
    if style_placeholder and normalized_reference.startswith("/media/"):
        return style_placeholder

    if normalized_reference.startswith(("http://", "https://", "/")):
        return normalized_reference

    if not settings.SUPABASE_USE_REMOTE_STORAGE:
        return normalized_reference

    client = get_supabase_client()
    if client is None:
        return normalized_reference

    bucket = client.storage.from_(settings.SUPABASE_BUCKET)
    if settings.SUPABASE_BUCKET_PUBLIC:
        return bucket.get_public_url(normalized_reference)

    try:
        signed = bucket.create_signed_url(normalized_reference, settings.SUPABASE_SIGNED_URL_EXPIRES_IN)
    except Exception as exc:
        if style_placeholder:
            return style_placeholder
        logger.warning("[storage] unable to resolve signed url for reference=%s: %s", normalized_reference, exc)
        return None
    resolved = _extract_signed_url(signed) or None
    if resolved:
        return resolved
    if style_placeholder:
        return style_placeholder
    return None


def _resolve_storage_reference_with_status(reference: str | None) -> tuple[str | None, str]:
    if not reference:
        return reference, "missing_reference"

    normalized_reference = str(reference).strip()
    if normalized_reference.startswith("data:image/"):
        return normalized_reference, "data_url"

    style_placeholder = _style_placeholder_if_missing(normalized_reference)
    if style_placeholder and normalized_reference.startswith("/media/"):
        return style_placeholder, "style_placeholder"

    if normalized_reference.startswith(("http://", "https://", "/")):
        return normalized_reference, "already_resolved"

    if not settings.SUPABASE_USE_REMOTE_STORAGE:
        return normalized_reference, "local_reference"

    client = get_supabase_client()
    if client is None:
        return None, "storage_client_unavailable"

    bucket = client.storage.from_(settings.SUPABASE_BUCKET)
    if settings.SUPABASE_BUCKET_PUBLIC:
        return bucket.get_public_url(normalized_reference), "public_url"

    try:
        signed = bucket.create_signed_url(normalized_reference, settings.SUPABASE_SIGNED_URL_EXPIRES_IN)
    except Exception as exc:
        if style_placeholder:
            return style_placeholder, "style_placeholder"
        logger.warning("[storage] unable to resolve signed url for reference=%s: %s", normalized_reference, exc)
        return None, "signed_url_failed"

    resolved = _extract_signed_url(signed)
    if resolved:
        return resolved, "signed_url"
    if style_placeholder:
        return style_placeholder, "style_placeholder"
    return None, "signed_url_unresolved"


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
