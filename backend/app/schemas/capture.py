from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

class BaseSchema(BaseModel):
    model_config = ConfigDict(
        use_enum_values=True,
        from_attributes=True,
        populate_by_name=True
    )

class CaptureMetadata(BaseSchema):
    customer_id: int = Field(..., gt=0, description="고객 고유 ID")

class CaptureUpdate(BaseSchema):
    status: Optional[str] = None
    face_count: Optional[int] = None

class CaptureResponse(BaseSchema):
    id: int
    customer_id: int
    status: str
    filename: str
    face_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime

class CaptureUploadResult(BaseSchema):
    status: str = "success"
    record_id: int