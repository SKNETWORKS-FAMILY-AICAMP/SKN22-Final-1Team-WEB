from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class FaceAnalysisResponse(BaseModel):
    id: int
    customer_id: int
    face_shape: Optional[str] = None
    golden_ratio_score: Optional[float] = None
    image_url: Optional[str] = None
    
    class Config:
        from_attributes = True

class StyleSelectionCreate(BaseModel):
    style_id: int
    match_score: float

class StyleSelectionResponse(BaseModel):
    id: int
    customer_id: int
    style_id: int
    match_score: float
    is_sent_to_designer: bool
    created_at: datetime
    
    class Config:
        from_attributes = True
