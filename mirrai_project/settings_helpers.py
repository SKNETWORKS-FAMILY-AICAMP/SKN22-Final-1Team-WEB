from __future__ import annotations

import logging
import socket
from urllib.parse import urlparse
from urllib.request import urlopen

try:
    import redis
except Exception:  # pragma: no cover - optional dependency failure
    redis = None


logger = logging.getLogger(__name__)


def _is_local_redis_url(redis_url: str) -> bool:
    normalized_url = str(redis_url or "").strip()
    if not normalized_url:
        return False
    try:
        hostname = (urlparse(normalized_url).hostname or "").strip().lower()
    except Exception:
        return False
    return hostname in {"127.0.0.1", "localhost", "::1"}


def unique_values(*groups) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for group in groups:
        for raw_value in group or []:
            value = str(raw_value or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            values.append(value)
    return values


def metadata_local_ipv4(*, timeout: float = 0.2) -> str | None:
    try:
        with urlopen("http://169.254.169.254/latest/meta-data/local-ipv4", timeout=timeout) as response:
            return response.read().decode("utf-8").strip()
    except Exception:
        return None


def build_allowed_hosts(*, default_hosts: list[str], env_hosts: list[str]) -> list[str]:
    dynamic_hosts = [
        metadata_local_ipv4(),
        socket.gethostname(),
    ]
    try:
        dynamic_hosts.append(socket.gethostbyname(socket.gethostname()))
    except OSError:
        pass
    return unique_values(default_hosts, env_hosts, dynamic_hosts)


def resolve_active_database_url(
    *,
    supabase_use_remote_db: bool,
    supabase_db_url: str,
    local_database_url: str,
    database_url: str,
) -> str:
    if supabase_use_remote_db and str(supabase_db_url or "").strip():
        return str(supabase_db_url).strip()
    if str(local_database_url or "").strip():
        return str(local_database_url).strip()
    if str(database_url or "").strip():
        return str(database_url).strip()
    return "sqlite:///db.sqlite3"


def redis_cache_available(*, redis_url: str, health_timeout: float = 0.5) -> bool:
    normalized_url = str(redis_url or "").strip()
    if not normalized_url:
        return False
    local_redis = _is_local_redis_url(normalized_url)
    if redis is None:
        log = logger.debug if local_redis else logger.warning
        log("[settings] redis package unavailable; using local memory cache instead.")
        return False
    try:
        client = redis.Redis.from_url(
            normalized_url,
            socket_connect_timeout=health_timeout,
            socket_timeout=health_timeout,
            health_check_interval=0,
        )
        try:
            client.ping()
        finally:
            client.close()
        return True
    except Exception as exc:
        log = logger.debug if local_redis else logger.warning
        log(
            "[settings] Redis unavailable at %s; using local memory cache instead. error=%s",
            normalized_url,
            exc,
        )
        return False


def build_cache_settings(*, redis_url: str, timeout: int, key_prefix: str) -> dict:
    normalized_url = str(redis_url or "").strip()
    if normalized_url:
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": normalized_url,
                "TIMEOUT": timeout,
                "KEY_PREFIX": key_prefix,
                "OPTIONS": {
                    "socket_connect_timeout": 5,
                    "socket_timeout": 5,
                    "retry_on_timeout": True,
                    "health_check_interval": 30,
                },
            }
        }

    return {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "mirrai-local-cache",
            "TIMEOUT": timeout,
            "KEY_PREFIX": key_prefix,
        }
    }
