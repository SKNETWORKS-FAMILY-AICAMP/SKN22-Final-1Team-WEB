from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.survey import SurveyCreate, SurveyResponse
from app.services import survey_service
from app import models
from app.api.v1.auth import get_current_user

router = APIRouter()


@router.post("/submit", response_model=SurveyResponse)
def submit_survey(
    survey_in: SurveyCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    survey_in.customer_id = current_user.id

    try:
        return survey_service.create_survey(db, survey_in)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"설문 처리 실패: {str(e)}")
