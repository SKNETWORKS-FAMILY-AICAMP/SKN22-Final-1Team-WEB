from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.core.database import Base

class CaptureRecord(Base):
    __tablename__ = "capture_records"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    
    original_path = Column(String(500), nullable=False)
    processed_path = Column(String(500), nullable=False)
    filename = Column(String(255), nullable=False)
    
    status = Column(String(50), default="PENDING", index=True)
    face_count = Column(Integer, nullable=True)
    
    error_note = Column(String(1000), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    customer = relationship("Customer", back_populates="captures")