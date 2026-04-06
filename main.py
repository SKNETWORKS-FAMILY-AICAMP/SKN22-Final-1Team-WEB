import logging
import os
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import boto3
import environ
from botocore.exceptions import ClientError
from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.recommendation_logic import score_recommendations


logger = logging.getLogger("mirrai.ai")
app = FastAPI(title="MirrAI Internal AI Service")

APP_STARTED_AT = time.time()
SCHEMA_VERSION = "2026-04-06"
RESPONSE_VERSION = "1.2.0"
DEV_BASE_URL = "http://localhost:8000"
PROD_BASE_URL = "https://mirrai.shop"

ENV_PATH = Path(__file__).resolve().parent / ".env"
if ENV_PATH.exists():
    environ.Env.read_env(ENV_PATH)


def _get_bedrock_client():
    try:
        return boto3.client("bedrock-runtime", region_name="us-east-1")
    except Exception as exc:
        logger.error("Failed to initialize Bedrock client: %s", exc)
        return None


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=RESPONSE_VERSION,
        description="Internal AI service for MirrAI recommendation generation and explanation.",
        routes=app.routes,
    )
    openapi_schema["servers"] = [
        {"url": DEV_BASE_URL, "description": "development"},
        {"url": PROD_BASE_URL, "description": "production"},
    ]
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


class AnalyzeFaceRequest(BaseModel):
    image_url: str | None = None
    image_base64: str | None = None


class GenerateSimulationsRequest(BaseModel):
    client_id: int
    survey_data: dict = Field(default_factory=dict)
    analysis_data: dict


class ExplainStyleRequest(BaseModel):
    card: dict


def _internal_api_token() -> str:
    return os.environ.get("MIRRAI_INTERNAL_API_TOKEN", "").strip()


def _legacy_internal_api_key() -> str:
    return os.environ.get("MIRRAI_INTERNAL_API_KEY", "").strip()


def _require_internal_auth(
    *,
    authorization: str | None,
    x_internal_api_key: str | None,
) -> tuple[bool, str | None]:
    configured_token = _internal_api_token()
    configured_legacy_key = _legacy_internal_api_key()
    if not configured_token and not configured_legacy_key:
        return True, None

    bearer_token = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer_token = authorization.split(" ", 1)[1].strip()

    if configured_token and bearer_token == configured_token:
        return True, "bearer"
    if configured_legacy_key and (x_internal_api_key or "").strip() == configured_legacy_key:
        return True, "legacy_api_key"
    return False, None


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", uuid.uuid4().hex)


def _processing_time_ms(request: Request) -> int:
    started_at = getattr(request.state, "started_at", time.perf_counter())
    return max(0, int((time.perf_counter() - started_at) * 1000))


def _success_payload(
    *,
    request: Request,
    data: dict[str, Any],
    status_text: str = "success",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "status": status_text,
        "schema_version": SCHEMA_VERSION,
        "response_version": RESPONSE_VERSION,
        "request_id": _request_id(request),
        "processing_time_ms": _processing_time_ms(request),
        "data": data,
    }
    if extra:
        payload.update(extra)
    return payload


def _error_payload(
    *,
    request: Request,
    error_code: str,
    message: str,
    detail: Any = None,
    retryable: bool = False,
) -> dict[str, Any]:
    return {
        "status": "error",
        "schema_version": SCHEMA_VERSION,
        "response_version": RESPONSE_VERSION,
        "request_id": _request_id(request),
        "processing_time_ms": _processing_time_ms(request),
        "error_code": error_code,
        "message": message,
        "detail": detail,
        "retryable": retryable,
    }


def _simulate_face_analysis(image_url: str | None = None, image_base64: str | None = None) -> dict[str, Any]:
    return {
        "face_shape": "Oval",
        "golden_ratio_score": 0.92,
        "face_ratios": {
            "cheekbone_to_height": 0.34,
            "jaw_to_height": 0.27,
            "temple_to_height": 0.58,
            "jaw_to_cheekbone": 1.12,
        },
        "face_bbox": {
            "x": 144,
            "y": 92,
            "width": 480,
            "height": 620,
        },
        "image_url": image_url,
        "visualization": {
            "image_url": image_url,
            "source": "local_stub" if image_url or image_base64 else "no_image",
        },
    }


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex
    request.state.started_at = time.perf_counter()
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=_error_payload(
            request=request,
            error_code="invalid_request",
            message="Request validation failed.",
            detail=exc.errors(),
            retryable=False,
        ),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    message = str(detail)
    if isinstance(detail, dict):
        message = detail.get("message") or message
    retryable = exc.status_code in {429, 502, 503}
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(
            request=request,
            error_code=f"http_{exc.status_code}",
            message=message,
            detail=detail,
            retryable=retryable,
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled internal AI service exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=_error_payload(
            request=request,
            error_code="internal_server_error",
            message="The internal AI service failed unexpectedly.",
            detail=str(exc),
            retryable=False,
        ),
    )


@app.get("/")
async def root(request: Request):
    return _success_payload(
        request=request,
        data={
            "service": "mirrai-internal-ai",
            "message": "Internal AI service for analysis and recommendation generation.",
        },
    )


@app.get("/internal/health")
async def internal_health(
    request: Request,
    authorization: str | None = Header(default=None),
    x_internal_api_key: str | None = Header(default=None, alias="X-Internal-API-Key"),
    x_mirrai_api_version: str | None = Header(default=None, alias="X-MirrAI-API-Version"),
):
    authorized, auth_mode = _require_internal_auth(
        authorization=authorization,
        x_internal_api_key=x_internal_api_key,
    )
    if not authorized:
        return JSONResponse(
            status_code=401,
            content=_error_payload(
                request=request,
                error_code="unauthorized",
                message="A valid internal API token is required.",
                detail="Use Authorization: Bearer <MIRRAI_INTERNAL_API_TOKEN> or X-Internal-API-Key.",
                retryable=False,
            ),
        )

    return _success_payload(
        request=request,
        data={
            "role": "ai-microservice",
            "build_version": os.environ.get("MIRRAI_AI_BUILD_VERSION", RESPONSE_VERSION),
            "model_version": os.environ.get("MIRRAI_MODEL_VERSION", "local-stub"),
            "uptime_seconds": int(time.time() - APP_STARTED_AT),
            "requested_api_version": x_mirrai_api_version,
            "auth_mode": auth_mode,
        },
    )


@app.post("/internal/analyze-face")
async def analyze_face(
    payload: AnalyzeFaceRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    x_internal_api_key: str | None = Header(default=None, alias="X-Internal-API-Key"),
):
    authorized, _ = _require_internal_auth(
        authorization=authorization,
        x_internal_api_key=x_internal_api_key,
    )
    if not authorized:
        return JSONResponse(
            status_code=401,
            content=_error_payload(
                request=request,
                error_code="unauthorized",
                message="A valid internal API token is required.",
                detail=None,
                retryable=False,
            ),
        )

    if not payload.image_url and not payload.image_base64:
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                request=request,
                error_code="missing_image",
                message="Either image_url or image_base64 must be provided.",
                detail={"required": ["image_url", "image_base64"]},
                retryable=False,
            ),
        )

    return _success_payload(
        request=request,
        data=_simulate_face_analysis(
            image_url=payload.image_url,
            image_base64=payload.image_base64,
        ),
    )


@app.post("/internal/generate-simulations")
async def generate_simulations(
    payload: GenerateSimulationsRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    x_internal_api_key: str | None = Header(default=None, alias="X-Internal-API-Key"),
):
    authorized, _ = _require_internal_auth(
        authorization=authorization,
        x_internal_api_key=x_internal_api_key,
    )
    if not authorized:
        return JSONResponse(
            status_code=401,
            content=_error_payload(
                request=request,
                error_code="unauthorized",
                message="A valid internal API token is required.",
                detail=None,
                retryable=False,
            ),
        )

    survey = SimpleNamespace(client_id=payload.client_id, **(payload.survey_data or {}))
    analysis = SimpleNamespace(**payload.analysis_data)
    items = score_recommendations(survey=survey, analysis=analysis)
    return _success_payload(
        request=request,
        data={"items": items},
    )


@app.post("/internal/explain-style")
async def explain_style(
    payload: ExplainStyleRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    x_internal_api_key: str | None = Header(default=None, alias="X-Internal-API-Key"),
):
    authorized, _ = _require_internal_auth(
        authorization=authorization,
        x_internal_api_key=x_internal_api_key,
    )
    if not authorized:
        return JSONResponse(
            status_code=401,
            content=_error_payload(
                request=request,
                error_code="unauthorized",
                message="A valid internal API token is required.",
                detail=None,
                retryable=False,
            ),
        )

    card = payload.card or {}
    style_name = card.get("style_name", "this style")
    llm_explanation = card.get("llm_explanation")

    client = _get_bedrock_client()
    if client:
        try:
            if not llm_explanation:
                llm_explanation = f"AI Insight: {style_name} offers a modern look that enhances facial features."
        except ClientError as exc:
            logger.error("AWS Bedrock Permission/Service Error: %s", exc)
            llm_explanation = "현재 AI 기능을 사용할 수 없습니다. (AI 서비스 권한 오류)"
        except Exception as exc:
            logger.error("Unexpected error during AI explanation generation: %s", exc)
            llm_explanation = "현재 AI 기능을 사용할 수 없습니다."
    elif not llm_explanation:
        llm_explanation = "현재 AI 기능을 사용할 수 없습니다. (AI 서비스 연결 실패)"

    resolved_card = {
        **card,
        "style_id": card.get("style_id"),
        "style_name": style_name,
        "simulation_image_url": card.get("simulation_image_url"),
        "llm_explanation": llm_explanation,
    }
    return _success_payload(
        request=request,
        data={
            "style_id": card.get("style_id"),
            "style_name": style_name,
            "llm_explanation": llm_explanation,
            "simulation_image_url": card.get("simulation_image_url"),
            "card": resolved_card,
        },
    )
