import asyncio
import logging
from sqlalchemy import update
from app.core.database import SessionLocal
from app.models.capture import CaptureRecord

logger = logging.getLogger(__name__)

_pipeline_semaphore = None

def get_semaphore() -> asyncio.Semaphore:
    global _pipeline_semaphore
    if _pipeline_semaphore is None:
        _pipeline_semaphore = asyncio.Semaphore(2)
    return _pipeline_semaphore

async def run_mirrai_analysis_pipeline(record_id: int):
    """
    분석 파이프라인 워커:
    Atomic Update로 중복 실행을 방지하고, 전처리된(processed_path) 이미지를 처리함.
    """
    semaphore = get_semaphore()
    async with semaphore:
        db = SessionLocal()
        try:
            # 1. 원자적 상태 변경 (PENDING -> PROCESSING)
            stmt = (
                update(CaptureRecord)
                .where(CaptureRecord.id == record_id)
                .where(CaptureRecord.status == "PENDING")
                .values(status="PROCESSING")
            )
            result = db.execute(stmt)
            db.commit()

            if result.rowcount == 0:
                return

            record = db.get(CaptureRecord, record_id)
            if not record: return

            # [AI Simulation Step] 
            # 실제 운영 환경에서는 여기서 MediaPipe, HairCLIPv2 API를 호출합니다.
            from app.models.analysis import FaceAnalysis
            
            # 가상의 얼굴 분석 결과 생성
            analysis = FaceAnalysis(
                customer_id=record.customer_id,
                face_shape="타원형 (Oval)",
                golden_ratio_score=0.88,
                image_url=record.processed_path
            )
            db.add(analysis)
            
            # 파이프라인 완료 상태로 업데이트
            record.status = "DONE"
            db.commit()
            
            logger.info(f"[PIPELINE SUCCESS] Record {record_id} processed with face analysis.")
            
        except Exception as e:
            db.rollback()
            # 실패 시 상태 기록을 위한 새 트랜잭션
            record = db.get(CaptureRecord, record_id)
            if record:
                record.status = "FAILED"
                db.commit()
            logger.error(f"[PIPELINE ERROR] Record {record_id}: {str(e)}")
        finally:
            db.close()