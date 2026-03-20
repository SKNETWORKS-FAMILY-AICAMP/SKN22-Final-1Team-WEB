from sqlalchemy.orm import Session
from app import models
import logging

logger = logging.getLogger(__name__)


class SurveyVector:
    """
    사용자의 취향(Survey)과 안면 분석 데이터를 결합하여
    AI 모델(RunPod)에 전달할 최종 벡터를 생성하는 모듈.
    """

    def get_latest_vector(self, db: Session, customer_id: int):
        """DB에서 최신 설문을 가져와 AI 모델용 파라미터로 변환"""
        survey = (
            db.query(models.Survey)
            .filter(models.Survey.customer_id == customer_id)
            .order_by(models.Survey.id.desc())
            .first()
        )

        if not survey:
            return None

        return {
            "vibe_tag": survey.target_vibe.value,
            "length_constraint": survey.current_length.value,
            "color_hex": self._map_color_to_hex(survey.hair_colour),
            "budget_limit": survey.budget_range.value,
        }

    def _map_color_to_hex(self, color_enum):
        # 예시: AI 모델이 이해할 수 있는 색상 코드로 매핑
        mapping = {"BLACK": "#000000", "BROWN": "#4B2C20"}
        return mapping.get(color_enum.name, "#000000")


survey_vector = SurveyVector()
