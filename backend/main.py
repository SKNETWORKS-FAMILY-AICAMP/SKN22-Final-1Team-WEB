import logging
from types import SimpleNamespace

import boto3
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field

from app.api.v1.recommendation_logic import score_recommendations


logger = logging.getLogger("mirrai.ai")
app = FastAPI(title="MirrAI Internal AI Service")


def _get_bedrock_client():
    """
    Returns a Bedrock runtime client. 
    Wrapped in try-except to catch potential AWS credential/permission issues at initialization.
    """
    try:
        # AWS region is typically required for Bedrock. Using us-east-1 as a default for testing.
        return boto3.client("bedrock-runtime", region_name="us-east-1")
    except Exception as exc:
        logger.error("Failed to initialize Bedrock client: %s", exc)
        return None


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version="1.1.0",
        description="Internal AI service for MirrAI recommendation generation and explanation.",
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


class AnalyzeFaceRequest(BaseModel):
    image_url: str | None = None
    image_base64: str | None = None


class AnalyzeFaceResponse(BaseModel):
    face_shape: str
    golden_ratio_score: float
    image_url: str | None = None


class GenerateSimulationsRequest(BaseModel):
    client_id: int
    survey_data: dict = Field(default_factory=dict)
    analysis_data: dict


class GenerateSimulationsResponse(BaseModel):
    status: str
    items: list[dict]


class ExplainStyleRequest(BaseModel):
    card: dict


class ExplainStyleResponse(BaseModel):
    style_id: int | None = None
    style_name: str | None = None
    sample_image_url: str | None = None
    simulation_image_url: str | None = None
    llm_explanation: str | None = None
    keywords: list[str] = Field(default_factory=list)


def _simulate_face_analysis(image_url: str | None = None, image_base64: str | None = None) -> dict:
    return {
        "face_shape": "Oval",
        "golden_ratio_score": 0.92,
        "image_url": image_url,
    }


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "mirrai-internal-ai",
        "message": "Internal AI service for analysis and recommendation generation.",
    }


@app.get("/internal/health")
async def internal_health():
    return {"status": "ok", "role": "ai-microservice"}


@app.post("/internal/analyze-face", response_model=AnalyzeFaceResponse)
async def analyze_face(payload: AnalyzeFaceRequest):
    return _simulate_face_analysis(image_url=payload.image_url, image_base64=payload.image_base64)


@app.post("/internal/generate-simulations", response_model=GenerateSimulationsResponse)
async def generate_simulations(payload: GenerateSimulationsRequest):
    survey = SimpleNamespace(client_id=payload.client_id, **(payload.survey_data or {}))
    analysis = SimpleNamespace(**payload.analysis_data)
    items = score_recommendations(survey=survey, analysis=analysis)
    return {"status": "ready", "items": items}


@app.post("/internal/explain-style", response_model=ExplainStyleResponse)
async def explain_style(payload: ExplainStyleRequest):
    card = payload.card or {}
    style_name = card.get("style_name", "this style")
    
    # AI Explanation via AWS Bedrock
    llm_explanation = card.get("llm_explanation")
    
    client = _get_bedrock_client()
    if client:
        try:
            # Simple prompt for style explanation - normally you'd use a more complex prompt.
            # Here we wrap it in a try-except specifically for AWS/Bedrock service errors.
            prompt = f"Explain why {style_name} is a good hair style for a customer based on professional styling trends."
            
            # This is a simulation/placeholder for a real Bedrock model invocation.
            # In a real scenario, you'd use client.invoke_model(...)
            # If a ClientError (permissions/throttling) occurs, it will be caught below.
            
            # Simulation of a permission error if needed (uncomment to test):
            # raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "No permission"}}, "InvokeModel")
            
            # If everything is fine, we might append or replace the static explanation.
            if not llm_explanation:
                llm_explanation = f"AI Insight: {style_name} offers a modern look that enhances facial features."
                
        except ClientError as exc:
            # Handle AWS Specific Errors (like Permission Issues)
            logger.error("AWS Bedrock Permission/Service Error: %s", exc)
            llm_explanation = "현재 AI 기능을 사용할 수 없습니다. (AI 서비스 권한 오류)"
        except Exception as exc:
            # Handle general errors
            logger.error("Unexpected error during AI explanation generation: %s", exc)
            llm_explanation = "현재 AI 기능을 사용할 수 없습니다."
    else:
        # Client initialization failed (already logged in _get_bedrock_client)
        if not llm_explanation:
            llm_explanation = "현재 AI 기능을 사용할 수 없습니다. (AI 서비스 연결 실패)"

    return {
        "style_id": card.get("style_id"),
        "style_name": style_name,
        "sample_image_url": card.get("sample_image_url"),
        "simulation_image_url": card.get("simulation_image_url"),
        "llm_explanation": llm_explanation,
        "keywords": card.get("keywords", []),
    }

