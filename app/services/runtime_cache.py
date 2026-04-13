from __future__ import annotations

import hashlib
import json
import logging
from copy import deepcopy
from typing import Any

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def cache_timeout(setting_name: str, default: int) -> int:
    value = getattr(settings, setting_name, default)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _cache_get_raw(key: str):
    try:
        return cache.get(key)
    except Exception as exc:
        logger.warning("[runtime_cache] cache.get failed key=%s error=%s", key, exc)
        return None


def _cache_set_raw(key: str, value, timeout: int | None) -> None:
    try:
        cache.set(key, value, timeout)
    except Exception as exc:
        logger.warning("[runtime_cache] cache.set failed key=%s error=%s", key, exc)


def _cache_add_raw(key: str, value, timeout: int | None) -> bool:
    try:
        return bool(cache.add(key, value, timeout))
    except Exception as exc:
        logger.warning("[runtime_cache] cache.add failed key=%s error=%s", key, exc)
        return False


def _cache_incr_raw(key: str) -> bool:
    try:
        cache.incr(key)
        return True
    except Exception as exc:
        logger.warning("[runtime_cache] cache.incr failed key=%s error=%s", key, exc)
        return False


def get_cached_payload(key: str):
    payload = _cache_get_raw(key)
    if payload is None:
        return None
    return deepcopy(payload)


def set_cached_payload(key: str, payload, *, timeout: int | None = None):
    effective_timeout = timeout if timeout is not None else cache_timeout("CACHE_DEFAULT_TIMEOUT", 300)
    _cache_set_raw(key, deepcopy(payload), effective_timeout)
    return payload


def _first_attr(obj: Any, *attr_names: str) -> str:
    if obj is None:
        return "none"

    for attr_name in attr_names:
        value = getattr(obj, attr_name, None)
        if value not in (None, ""):
            return str(value).strip()
    return "none"


def _admin_identity(admin=None) -> str:
    return _first_attr(admin, "id", "admin_id", "backend_admin_id", "legacy_admin_id")


def _designer_identity(designer=None) -> str:
    return _first_attr(designer, "id", "designer_id", "backend_designer_id", "legacy_designer_id")


def _client_identity(client=None) -> str:
    return _first_attr(client, "id", "client_id", "backend_client_id", "legacy_client_id")


def _scope_identity(*, admin=None, designer=None) -> str:
    return f"admin:{_admin_identity(admin)}:designer:{_designer_identity(designer)}"


def _version_key(namespace: str, identity: str) -> str:
    prefix = getattr(settings, "REDIS_KEY_PREFIX", "mirrai")
    return f"{prefix}:cache-version:{namespace}:{identity}"


def _ensure_version(key: str) -> int:
    value = _cache_get_raw(key)
    if value is None:
        _cache_add_raw(key, 1, None)
        value = _cache_get_raw(key)
    try:
        return int(value or 1)
    except (TypeError, ValueError):
        _cache_set_raw(key, 1, None)
        return 1


def _bump_version(key: str) -> None:
    if _cache_add_raw(key, 2, None):
        return
    if not _cache_incr_raw(key):
        _cache_set_raw(key, 2, None)


def build_partner_cache_key(
    prefix: str,
    *,
    admin=None,
    designer=None,
    client=None,
    extras: dict[str, Any] | None = None,
) -> str:
    scope_identity = _scope_identity(admin=admin, designer=designer)
    scope_version = _ensure_version(_version_key("scope", scope_identity))
    payload = {
        "prefix": prefix,
        "scope": scope_identity,
        "scope_version": scope_version,
    }

    client_identity = _client_identity(client)
    if client_identity != "none":
        payload["client"] = client_identity
        payload["client_version"] = _ensure_version(_version_key("client", client_identity))

    if extras:
        payload["extras"] = extras

    serialized = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    digest = hashlib.sha1(serialized.encode("utf-8")).hexdigest()
    prefix_root = getattr(settings, "REDIS_KEY_PREFIX", "mirrai")
    return f"{prefix_root}:cache:{prefix}:{digest}"


def invalidate_partner_scope_cache(*, admin=None, designer=None) -> None:
    _bump_version(_version_key("scope", _scope_identity(admin=admin, designer=designer)))


def invalidate_partner_client_cache(*, client=None, admin=None, designer=None) -> None:
    client_identity = _client_identity(client)
    if client_identity != "none":
        _bump_version(_version_key("client", client_identity))

    resolved_admin = admin or getattr(designer, "shop", None) or getattr(client, "shop", None)
    resolved_designer = designer or getattr(client, "designer", None)

    scopes = set()
    if resolved_admin is not None:
        scopes.add(_scope_identity(admin=resolved_admin, designer=None))
    if resolved_admin is not None and resolved_designer is not None:
        scopes.add(_scope_identity(admin=resolved_admin, designer=resolved_designer))

    for scope_identity in scopes:
        _bump_version(_version_key("scope", scope_identity))
