from sqlalchemy import Column, Integer, ForeignKey, Enum as SQLEnum, DateTime, func, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.enums import CurrentLength, TargetVibe, ScalpType, HairColour, BudgetRange

class Survey(Base):
    __tablename__ = "surveys"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True, unique=True)

    current_length = Column(SQLEnum(CurrentLength, native_enum=False), nullable=False)
    target_vibe = Column(SQLEnum(TargetVibe, native_enum=False), nullable=False)
    scalp_type = Column(SQLEnum(ScalpType, native_enum=False), nullable=False)
    hair_colour = Column(SQLEnum(HairColour, native_enum=False), nullable=False)
    budget_range = Column(SQLEnum(BudgetRange, native_enum=False), nullable=False)

    preference_vector = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    customer = relationship("Customer", back_populates="surveys")