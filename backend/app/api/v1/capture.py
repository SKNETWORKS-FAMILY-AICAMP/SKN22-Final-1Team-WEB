from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks, status
from sqlalchemy.orm import Session
import os
import asyncio
from app.core.database import get_db
from app.models.capture import CaptureRecord
from app.schemas.capture import CaptureUploadResult
from app.services.image_service import ImageService
from app.services.pipeline_service import run_mirrai_analysis_pipeline
from app.api.v1.auth import get_current_user
from app import models  # 수정됨: 절대 경로 임포트로 Unresolved Reference 해결

router = APIRouter()
image_service = ImageService()

@router.post("/upload", response_model=CaptureUploadResult)
async def upload_capture(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    original_path = ""
    processed_path = ""
    try:
        original_path = await image_service.save_image(file)
        
        processed_path = await asyncio.to_thread(
            image_service.create_processed_image, 
            original_path
        )

        new_record = CaptureRecord(
            customer_id=current_user.id,
            original_path=original_path,
            processed_path=processed_path,
            filename=file.filename,
            status="PENDING"
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        background_tasks.add_task(run_mirrai_analysis_pipeline, new_record.id)

        return {"status": "success", "record_id": new_record.id}

    except Exception as e:
        db.rollback()
        for p in [original_path, processed_path]:
            if p and os.path.exists(p):
                os.remove(p)

        if isinstance(e, HTTPException):
            raise e

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"업로드 처리 중 오류 발생: {str(e)}"
        )