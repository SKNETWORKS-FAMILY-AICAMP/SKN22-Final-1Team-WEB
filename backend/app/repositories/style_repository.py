from app.repositories.base import BaseRepository
from app.models.capture import CaptureRecord
from typing import List

class CaptureRepository(BaseRepository[CaptureRecord]):
    """CaptureRecord에 특화된 쿼리 확장"""
    def find_by_customer(self, customer_id: int) -> List[CaptureRecord]:
        return self.db.query(self.model).filter(
            self.model.customer_id == customer_id
        ).order_by(self.model.created_at.desc()).all()
    
    def get_pending_tasks(self) -> List[CaptureRecord]:
        return self.db.query(self.model).filter(
            self.model.status == "PENDING"
        ).all()