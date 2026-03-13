from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import time
import os
import boto3
from botocore.exceptions import ClientError
from pydantic import BaseModel

# 1. 메타데이터가 포함된 FastAPI 앱 생성
app = FastAPI(
    title="MirrAI (sAIon) API",
    description="얼굴형 및 취향 기반 헤어스타일 추천 시뮬레이션 웹 서비스 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None, # Redoc은 사용하지 않음
)

# 2. CORS 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: 운영 배포 시 특정 도메인으로 제한 필요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. 전역 에러 핸들러 (커스텀 에러 응답 포맷)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # 외부 시스템 연동, AI 모델 분석 중 에러가 발생한 경우를 대비한 공통 포맷
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "message": "서버 내부 오류가 발생했습니다.",
            "detail": str(exc),
            "timestamp": time.time()
        }
    )

# 4. Health Check API (AWS ALB 대상 그룹 타겟 검증 및 로컬 확인용)
@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "message": "MirrAI Backend is running smoothly."}

# [API 라우터 추가 예정 공간]
# app.include_router(user_router, prefix="/api/v1/users")
# app.include_router(recommend_router, prefix="/api/v1/recommend")

# 5. S3 Presigned URL 발급 API
# S3 클라이언트 전역 초기화 (Boto3 Session 병목 방지)
s3_client = boto3.client(
    's3',
    region_name=os.getenv('AWS_REGION', 'ap-northeast-2')
)

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/jpg", "image/webp"}

class PresignedUrlRequest(BaseModel):
    filename: str
    file_type: str

@app.post("/api/v1/upload/presigned-url", tags=["Upload"])
async def get_presigned_url(request_data: PresignedUrlRequest):
    # 파일 확장자(MIME Type) 화이트리스트 검증 (Critical 보안 이슈 해결)
    if request_data.file_type not in ALLOWED_MIME_TYPES:
        return JSONResponse(
            status_code=400,
            content={"error": True, "message": "지원하지 않는 파일 형식입니다. (JPG, PNG, WEBP만 허용)"}
        )

    bucket_name = os.getenv('S3_BUCKET_NAME', 'mirrai-user-images-dev')
    
    # 충돌 방지용 접두어(timestamp) 추가
    object_name = f"uploads/{int(time.time())}_{request_data.filename}"
    
    try:
        response = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket_name,
                'Key': object_name,
                'ContentType': request_data.file_type
            },
            ExpiresIn=3600
        )
    except ClientError as e:
        return JSONResponse(
            status_code=500,
            content={"error": True, "message": "S3 URL 발급 실패", "detail": str(e)}
        )
    
    return {
        "presigned_url": response,
        "object_key": object_name,
        "file_url": f"https://{bucket_name}.s3.ap-northeast-2.amazonaws.com/{object_name}"
    }
