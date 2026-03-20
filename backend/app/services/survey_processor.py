import logging
from typing import List
from app.models.survey import Survey
from app.models.enums import (
    CurrentLength,
    TargetVibe,
    ScalpType,
    HairColour,
    BudgetRange,
)

logger = logging.getLogger(__name__)

LENGTH_ORDER = [CurrentLength.SHORT, CurrentLength.BOB, CurrentLength.SEMILONG, CurrentLength.LONG]
VIBE_ORDER = [TargetVibe.CUTE, TargetVibe.CHIC, TargetVibe.NATURAL, TargetVibe.ELEGANT]
SCALP_ORDER = [ScalpType.STRAIGHT, ScalpType.WAVED, ScalpType.CURLY, ScalpType.DAMAGED]
COLOUR_ORDER = [HairColour.BLACK, HairColour.BROWN, HairColour.ASHEN, HairColour.BLEACHED]
BUDGET_ORDER = [BudgetRange.BELOW3, BudgetRange.FROM3TO5, BudgetRange.FROM5TO10, BudgetRange.OVER10]

def _one_hot(value, order_list) -> List[float]:
    """지정된 Enum 값 배열에 맞춰 One-Hot Vector 생성"""
    vector = [0.0] * len(order_list)
    if value in order_list:
        vector[order_list.index(value)] = 1.0
    return vector

def vectorize_customer_preferences(survey: Survey) -> List[float]:
    """
    AI 팀 가이드라인: 5가지 취향 설문 응답을 원-핫 인코딩하여 user_preference_vector 생성.
    (Length 4 + Vibe 4 + Scalp 4 + Colour 4 + Budget 4 = Total 20-dim Vector)
    """
    try:
        vector = []
        vector.extend(_one_hot(survey.current_length, LENGTH_ORDER))
        vector.extend(_one_hot(survey.target_vibe, VIBE_ORDER))
        vector.extend(_one_hot(survey.scalp_type, SCALP_ORDER))
        vector.extend(_one_hot(survey.hair_colour, COLOUR_ORDER))
        vector.extend(_one_hot(survey.budget_range, BUDGET_ORDER))

        logger.debug(
            f"User {survey.customer_id} One-Hot Vectorization successful. Dim: {len(vector)}, Vector: {vector}"
        )
        return vector

    except Exception as e:
        logger.error(f"Vectorization failed for Survey ID {survey.id}: {str(e)}")
        return [0.0] * 20
