from __future__ import annotations

from collections.abc import Mapping

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import APIView


DEFAULT_ERROR_CODE_BY_STATUS: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "unsupported_media_type",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_error",
}


def get_error_contract_snapshot() -> dict:
    return {
        "mode": "compat_envelope",
        "fields": ["detail", "message", "error_code"],
        "envelope_supported": True,
        "detail_backward_compatible": True,
    }


def _default_error_code(status_code: int) -> str:
    return DEFAULT_ERROR_CODE_BY_STATUS.get(status_code, "error")


def detail_response(
    message: str,
    *,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    error_code: str | None = None,
    **extra: object,
) -> Response:
    payload = {
        "detail": message,
        "message": message,
        "error_code": error_code or _default_error_code(status_code),
    }
    payload.update(extra)
    return Response(payload, status=status_code)


def _extract_exception_message(detail: object) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list) and detail:
        first = detail[0]
        if isinstance(first, str):
            return first
    if isinstance(detail, Mapping):
        return "Validation failed."
    return "Request failed."


class CompatEnvelopeAPIView(APIView):
    """
    Preserve DRF exception behavior while adding a stable `message` and `error_code`
    envelope around the existing `detail` field.
    """

    def handle_exception(self, exc):  # type: ignore[override]
        response = super().handle_exception(exc)
        if response is None:
            return response

        status_code = response.status_code
        data = response.data

        if isinstance(exc, exceptions.ValidationError):
            message = _extract_exception_message(data)
            response.data = {
                "detail": data,
                "message": message,
                "error_code": "validation_error",
            }
            return response

        if isinstance(data, Mapping):
            detail = data.get("detail", data)
        else:
            detail = data

        message = _extract_exception_message(detail)

        if isinstance(exc, exceptions.NotAuthenticated):
            error_code = "not_authenticated"
        elif isinstance(exc, exceptions.AuthenticationFailed):
            error_code = "authentication_failed"
        elif isinstance(exc, exceptions.PermissionDenied):
            error_code = "permission_denied"
        elif isinstance(exc, exceptions.NotFound):
            error_code = "not_found"
        elif isinstance(exc, exceptions.ParseError):
            error_code = "parse_error"
        else:
            error_code = _default_error_code(status_code)

        response.data = {
            "detail": detail,
            "message": message,
            "error_code": error_code,
        }
        return response
