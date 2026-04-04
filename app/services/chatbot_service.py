from __future__ import annotations

import logging
import os
import re
from typing import Any

import requests
from django.utils import timezone


logger = logging.getLogger(__name__)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _model_chatbot_url() -> str:
    return os.environ.get("MIRRAI_MODEL_CHATBOT_URL", "").strip()


def _model_chatbot_timeout() -> tuple[int, int]:
    read_timeout = int(os.environ.get("MIRRAI_MODEL_CHATBOT_TIMEOUT", "8"))
    return (3, max(5, read_timeout))


def _extract_remote_reply(payload: dict[str, Any]) -> dict[str, Any] | None:
    reply = payload.get("reply") or payload.get("message") or payload.get("answer")
    if not reply:
        return None

    matched_sources = payload.get("matched_sources")
    if not isinstance(matched_sources, list):
        matched_sources = []

    return {
        "status": "success",
        "reply": str(reply),
        "timestamp": payload.get("timestamp") or timezone.now().isoformat(),
        "matched_sources": matched_sources,
        "dataset_source": payload.get("dataset_source") or "model_team_chatbot",
        "provider": "model_team",
    }


def _ask_model_team_chatbot(*, message: str, admin_name: str | None = None, store_name: str | None = None) -> dict[str, Any] | None:
    url = _model_chatbot_url()
    if not url:
        return None

    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("MIRRAI_MODEL_CHATBOT_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = requests.post(
            url,
            json={
                "message": message,
                "admin_name": admin_name,
                "store_name": store_name,
            },
            headers=headers,
            timeout=_model_chatbot_timeout(),
        )
        response.raise_for_status()
        payload = response.json()
        remote_reply = _extract_remote_reply(payload if isinstance(payload, dict) else {})
        if remote_reply is None:
            logger.warning("[model_chatbot_invalid_payload] url=%s payload_type=%s", url, type(payload).__name__)
            return None
        return remote_reply
    except (requests.RequestException, ValueError) as exc:
        logger.warning("[model_chatbot_unavailable] url=%s reason=%s", url, exc)
        return None


def _build_dummy_reply(*, message: str) -> dict[str, Any]:
    return {
        "status": "success",
        "reply": (
            "현재 백엔드 챗봇은 임시 더미 응답 모드입니다.\n"
            "모델 팀 챗봇 엔드포인트가 연결되면 실제 시술 가이드 답변으로 대체됩니다.\n"
            f"입력 질문: {message}"
        ),
        "timestamp": timezone.now().isoformat(),
        "matched_sources": [],
        "dataset_source": "dummy_chatbot_payload",
        "provider": "local_dummy",
    }


def get_chatbot_backend_status() -> dict[str, Any]:
    url = _model_chatbot_url()
    timeout = _model_chatbot_timeout()
    return {
        "provider_priority": "model_team_first",
        "remote_configured": bool(url),
        "remote_url": url or None,
        "timeout": {
            "connect_seconds": timeout[0],
            "read_seconds": timeout[1],
        },
        "fallback_provider": "local_dummy",
    }


def build_admin_chatbot_reply(*, message: str, admin_name: str | None = None, store_name: str | None = None) -> dict[str, Any]:
    question = _normalize_text(message)
    if not question:
        raise ValueError("message is required.")

    remote_reply = _ask_model_team_chatbot(
        message=question,
        admin_name=admin_name,
        store_name=store_name,
    )
    if remote_reply is not None:
        remote_reply["admin_name"] = admin_name
        remote_reply["store_name"] = store_name
        return remote_reply

    payload = _build_dummy_reply(message=question)
    payload["admin_name"] = admin_name
    payload["store_name"] = store_name
    return payload
