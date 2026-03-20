from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.schemas.analysis import FaceAnalysisResponse, StyleSelectionCreate, StyleSelectionResponse
# Importing modules locally to avoid circular dependencies if necessary
from app import models
from app.models.analysis import FaceAnalysis, StyleSelection

router = APIRouter()

@router.post("/upload", response_model=FaceAnalysisResponse)
async def upload_face_photo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    고객 정면 사진 업로드 및 AI 얼굴 분석 수행 (추후 AI 파이프라인 연동 대기)
    """
    # TODO: 환경변수 설정 후 외부 API 연동
    mock_image_url = f"/storage/{file.filename}"
    
    analysis = FaceAnalysis(
        customer_id=current_user.id,
        face_shape="타원형",
        golden_ratio_score=0.87,
        image_url=mock_image_url
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis

@router.post("/select", response_model=StyleSelectionResponse)
def select_style(
    selection: StyleSelectionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    선택된 스타일을 디자이너에게 전송 (DB 기록)
    """
    new_selection = StyleSelection(
        customer_id=current_user.id,
        style_id=selection.style_id,
        match_score=selection.match_score,
        is_sent_to_designer=True
    )
    db.add(new_selection)
    db.commit()
    db.refresh(new_selection)
    return new_selection

from pydantic import BaseModel
from typing import Optional

class RecommendationResponse(BaseModel):
    style_id: int
    style_name: str
    match_score: float
    reasoning: Optional[str] = None
    synthetic_image_url: Optional[str] = None

@router.get("/recommendations", response_model=list[RecommendationResponse])
def get_recommendations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    최신 설문 및 얼굴 분석 결과를 바탕으로 추천 Top-5 스타일 리스트와 가상 합성 이미지 반환
    """
    from app.models.survey import Survey
    from app.models.analysis import FaceAnalysis
    
    # 1. 최신 설문 데이터 확인
    latest_survey = db.query(Survey).filter(
        Survey.customer_id == current_user.id
    ).order_by(Survey.created_at.desc()).first()
    
    if not latest_survey:
        raise HTTPException(status_code=404, detail="설문 데이터가 없습니다. 먼저 설문을 진행해주세요.")
        
    # 2. 최신 얼굴 분석 데이터 확인
    latest_analysis = db.query(FaceAnalysis).filter(
        FaceAnalysis.customer_id == current_user.id
    ).order_by(FaceAnalysis.created_at.desc()).first()
    
    if not latest_analysis:
        raise HTTPException(status_code=404, detail="얼굴 분석 데이터가 없습니다. 먼저 사진을 업로드해주세요.")

    # 3. 추천 로직 시뮬레이션 (실제로는 ChromaDB RAG 연동)
    # 분석된 얼굴형(FaceAnalysis.face_shape)과 설문 벡터(latest_survey.preference_vector)를 조합
    face_type = latest_analysis.face_shape
    
    # 가상의 추천 리스트 생성
    mock_styles = [
        {"id": 101, "name": "시크 레이어드 컷", "vibe": "시크함", "suitability": 98},
        {"id": 102, "name": "내추럴 빌로우 펌", "vibe": "자연스러움", "suitability": 95},
        {"id": 103, "name": "엘레강트 그레이스 펌", "vibe": "우아함", "suitability": 92},
        {"id": 104, "name": "트렌디 보브 단발", "vibe": "시크함", "suitability": 89},
        {"id": 105, "name": "볼륨 매직 스트레이트", "vibe": "자연스러움", "suitability": 85},
    ]
    
    response = []
    for s in mock_styles:
        # 합성 이미지 URL 시뮬레이션 (원본 이미지 경로를 포함하여 AI 합성 결과임을 나타냄)
        synthetic_url = f"/storage/synthetic/{current_user.id}_{s['id']}_result.jpg"
        
        reason = f"분석된 '{face_type}' 얼굴형과 고객님의 '{latest_survey.target_vibe}' 지향점의 조화도가 {s['suitability']}%로 매우 높습니다."
        
        response.append({
            "style_id": s["id"],
            "style_name": s["name"],
            "match_score": float(s["suitability"]),
            "reasoning": reason,
            "synthetic_image_url": synthetic_url
        })
        
    return response
