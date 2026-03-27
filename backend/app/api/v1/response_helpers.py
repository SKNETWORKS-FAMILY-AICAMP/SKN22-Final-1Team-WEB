from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response


def get_error_contract_snapshot() -> dict:
    return {
        "mode": "drf_detail",
        "fields": ["detail"],
        "envelope_supported": False,
    }


def detail_response(
    message: str,
    *,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    **extra: object,
) -> Response:
    payload = {"detail": message}
    payload.update(extra)
    return Response(payload, status=status_code)
