from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional
from datetime import datetime
import re

class CustomerBase(BaseModel):
    """고객 스키마 공통 설정"""
    model_config = ConfigDict(from_attributes=True)

class LoginRequest(BaseModel):
    phone: str = Field(..., description="조회할 고객의 전화번호", example="010-1234-5678")

class CustomerCheck(CustomerBase):
    phone: str = Field(..., description="조회할 고객의 전화번호", example="010-1234-5678")

class CustomerCreate(CustomerBase):
    name: str = Field(..., min_length=1, description="고객 성함", example="임요환")
    phone: str = Field(..., description="고객 연락처", example="010-1234-5678")
    gender: str = Field(None, description="성별 ('남성' 또는 '여성')", example="남성")

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        clean_number = re.sub(r'[- ]', '', v)
        
        if not (10 <= len(clean_number) <= 11):
            raise ValueError('전화번호 자릿수가 올바르지 않습니다. (10~11자리 필요)')

        if len(clean_number) == 11:
            return f"{clean_number[:3]}-{clean_number[3:7]}-{clean_number[7:]}"
        else:
            return f"{clean_number[:3]}-{clean_number[3:6]}-{clean_number[6:]}"

class CustomerResponse(CustomerBase):
    id: int
    name: str
    phone: str
    gender: Optional[str] = None
    created_at: datetime