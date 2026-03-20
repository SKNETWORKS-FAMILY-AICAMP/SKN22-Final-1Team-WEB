import os
import uuid
import logging
import shutil
import asyncio
from fastapi import UploadFile
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

class ImageService:
    def __init__(self):
        self.upload_dir = "storage/captures"
        os.makedirs(self.upload_dir, exist_ok=True)

    async def save_image(self, file: UploadFile) -> str:
        file_ext = os.path.splitext(file.filename)[1].lower()
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(self.upload_dir, unique_filename)

        content = await file.read()
        def _write_file():
            with open(file_path, "wb") as buffer:
                buffer.write(content)
                
        await asyncio.to_thread(_write_file)

        return file_path

    def create_processed_image(self, original_path: str) -> str:
        processed_path = original_path + ".processed.jpg"

        try:
            with Image.open(original_path) as img:
                img = ImageOps.exif_transpose(img)

                if img.mode != 'RGB':
                    img = img.convert('RGB')

                img.save(processed_path, "JPEG", quality=95, optimize=True)

            return processed_path

        except Exception as e:
            logger.error(f"Image processing failed: {str(e)}")

            if os.path.exists(processed_path):
                os.remove(processed_path)

            raise

    async def save_and_process(self, file: UploadFile) -> dict:
        """
        원본 저장 + 후처리 + 경로 반환
        DB 저장용 메타데이터 생성
        """
        original_path = await self.save_image(file)
        processed_path = await asyncio.to_thread(self.create_processed_image, original_path)

        return {
            "original_path": original_path,
            "processed_path": processed_path
        }