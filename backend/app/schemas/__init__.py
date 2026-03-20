from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List

class BaseSchema(BaseModel):
    model_config = ConfigDict(
        use_enum_values=True,
        from_attributes=True
    )

class CustomerCheck(BaseSchema):
    phone: str

class CustomerCreate(BaseSchema):
    name: str
    phone: str
    gender: Optional[str] = None