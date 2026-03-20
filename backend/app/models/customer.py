from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    gender = Column(String(10), nullable=True)
    phone = Column(String(20), unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 관계 설정: Customer가 주체가 됨
    surveys = relationship("Survey", back_populates="customer", cascade="all, delete-orphan")
    captures = relationship("CaptureRecord", back_populates="customer", cascade="all, delete-orphan")