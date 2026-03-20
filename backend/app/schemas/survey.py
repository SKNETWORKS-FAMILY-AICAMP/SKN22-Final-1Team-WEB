from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from app.models.enums import (
    CurrentLength,
    TargetVibe,
    ScalpType,
    HairColour,
    BudgetRange,
)


class SurveyCreate(BaseModel):
    customer_id: Optional[int] = Field(
        None, description="인증된 토큰에서 자동 주입됩니다."
    )
    current_length: CurrentLength
    target_vibe: TargetVibe
    scalp_type: ScalpType
    hair_colour: HairColour
    budget_range: BudgetRange


class SurveyResponse(BaseModel):
    id: int
    customer_id: int
    current_length: CurrentLength
    target_vibe: TargetVibe
    scalp_type: ScalpType
    hair_colour: HairColour
    budget_range: BudgetRange

    model_config = ConfigDict(from_attributes=True)
