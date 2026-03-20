import logging
import json
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.models.survey import Survey
from app.schemas.survey import SurveyCreate
from app.repositories import survey_repository
from app.services import survey_processor
from app.models.enums import CurrentLength, TargetVibe, HairColour

logger = logging.getLogger(__name__)


class SurveyServiceError(Exception):
    """Survey 서비스 전체에서 사용하는 기본 예외 클래스"""

    pass


class ValidationError(SurveyServiceError):
    def __init__(self, message, issues=None):
        self.message = message
        self.issues = issues or []
        super().__init__(self.message)


class UserNotFoundError(SurveyServiceError):
    pass


class DatabaseError(SurveyServiceError):
    pass


def validate_survey_logic(data: SurveyCreate):
    """설문 데이터 간의 논리적 모순을 검증합니다."""
    issues = []
    if (
        data.current_length == CurrentLength.SHORT
        and data.target_vibe == TargetVibe.ELEGANT
    ):
        issues.append(
            "현재 짧은 머리 길이로는 '우아함(ELEGANT)' 스타일 구현이 어렵습니다."
        )

    if (
        data.hair_colour == HairColour.BLEACHED
        and data.target_vibe == TargetVibe.ELEGANT
    ):
        issues.append("탈색 모발은 '우아함' 스타일 구현에 제약이 있을 수 있습니다.")

    if issues:
        logger.warning(f"Validation warning for user {data.customer_id}: {issues}")
        raise ValidationError("설문 응답 간 논리적 모순 발견.", issues=issues)


def create_survey(db: Session, survey_data: SurveyCreate) -> Survey:
    """설문을 저장하고 취향 벡터를 생성합니다 (Overwrite 전략)."""
    validate_survey_logic(survey_data)

    if not survey_repository.customer_exists(db, survey_data.customer_id):
        raise UserNotFoundError(
            f"User ID {survey_data.customer_id}를 찾을 수 없습니다."
        )

    try:
        # 기존 설문 삭제 로직 제거 (히스토리 누적)

        survey_dict = survey_data.model_dump()
        new_survey_obj = Survey(**survey_dict)

        vector = survey_processor.vectorize_customer_preferences(new_survey_obj)
        new_survey_obj.preference_vector = json.loads(json.dumps(vector))

        db.add(new_survey_obj)
        db.commit()
        db.refresh(new_survey_obj)

        return new_survey_obj

    except ValidationError:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database operation failed: {str(e)}")
        raise DatabaseError("데이터베이스 저장 중 오류가 발생했습니다.")
