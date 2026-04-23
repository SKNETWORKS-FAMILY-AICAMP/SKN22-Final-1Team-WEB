from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image


MIN_FACE_SIZE_RATIO = 0.08
MIN_BRIGHTNESS = 35.0
MAX_BRIGHTNESS = 220.0
MIN_SHARPNESS = 45.0

_FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def _detect_faces(
    gray: np.ndarray,
    *,
    scale_factor: float,
    min_neighbors: int,
    min_size: tuple[int, int],
):
    return _FACE_CASCADE.detectMultiScale(
        gray,
        scaleFactor=scale_factor,
        minNeighbors=min_neighbors,
        minSize=min_size,
    )


def _iou(face_a, face_b) -> float:
    ax, ay, aw, ah = [int(value) for value in face_a]
    bx, by, bw, bh = [int(value) for value in face_b]
    a_right = ax + aw
    a_bottom = ay + ah
    b_right = bx + bw
    b_bottom = by + bh

    inter_left = max(ax, bx)
    inter_top = max(ay, by)
    inter_right = min(a_right, b_right)
    inter_bottom = min(a_bottom, b_bottom)
    if inter_right <= inter_left or inter_bottom <= inter_top:
        return 0.0

    intersection = float((inter_right - inter_left) * (inter_bottom - inter_top))
    union = float((aw * ah) + (bw * bh) - intersection)
    if union <= 0:
        return 0.0
    return intersection / union


def _dedupe_faces(faces, *, iou_threshold: float = 0.35) -> list[tuple[int, int, int, int]]:
    candidates = [tuple(int(value) for value in face) for face in faces]
    candidates.sort(key=lambda row: row[2] * row[3], reverse=True)
    deduped: list[tuple[int, int, int, int]] = []
    for face in candidates:
        if any(_iou(face, existing) >= iou_threshold for existing in deduped):
            continue
        deduped.append(face)
    return deduped


def _select_candidate_faces(gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    primary_faces = _dedupe_faces(
        _detect_faces(
            gray,
            scale_factor=1.1,
            min_neighbors=5,
            min_size=(80, 80),
        )
    )
    if len(primary_faces) == 1:
        return primary_faces

    # Front already filters alignment and position aggressively, so backend
    # gives Haar one more chance before forcing retake on count mismatches.
    if len(primary_faces) == 0:
        equalized = cv2.equalizeHist(gray)
        relaxed_faces = _dedupe_faces(
            _detect_faces(
                equalized,
                scale_factor=1.05,
                min_neighbors=4,
                min_size=(72, 72),
            )
        )
        if len(relaxed_faces) == 1:
            return relaxed_faces
        return relaxed_faces

    stricter_faces = _dedupe_faces(
        _detect_faces(
            gray,
            scale_factor=1.12,
            min_neighbors=7,
            min_size=(96, 96),
        )
    )
    if len(stricter_faces) == 1:
        return stricter_faces
    return primary_faces


def _validation_thresholds() -> dict:
    return {
        "min_face_size_ratio": MIN_FACE_SIZE_RATIO,
        "min_brightness": MIN_BRIGHTNESS,
        "max_brightness": MAX_BRIGHTNESS,
        "min_sharpness": MIN_SHARPNESS,
    }


def _base_validation_payload(
    *,
    is_valid: bool,
    status: str,
    face_count: int,
    reason_code: str,
    message: str,
    brightness: float | None = None,
    sharpness: float | None = None,
    image_width: int | None = None,
    image_height: int | None = None,
    face_area_ratio: float | None = None,
) -> dict:
    return {
        "is_valid": is_valid,
        "status": status,
        "face_count": face_count,
        "reason_code": reason_code,
        "message": message,
        "diagnostics": {
            "brightness": (None if brightness is None else round(float(brightness), 2)),
            "sharpness": (None if sharpness is None else round(float(sharpness), 2)),
            "image_width": image_width,
            "image_height": image_height,
            "face_area_ratio": (None if face_area_ratio is None else round(float(face_area_ratio), 4)),
        },
        "thresholds": _validation_thresholds(),
    }


def build_capture_validation_snapshot(
    *,
    validation: dict,
    landmark_snapshot: dict | None = None,
    front_capture_context: dict | None = None,
) -> dict:
    diagnostics = dict(validation.get("diagnostics") or {})
    thresholds = dict(validation.get("thresholds") or _validation_thresholds())
    front_context = front_capture_context if isinstance(front_capture_context, dict) else None

    front_all_valid = None
    front_message_key = None
    front_checklist_summary = None
    if front_context is not None:
        if "all_valid" in front_context:
            front_all_valid = bool(front_context.get("all_valid"))
        front_message_key = front_context.get("message_key")
        front_checklist_summary = front_context.get("checklist_summary") or front_context.get("summary")

    return {
        "status": validation.get("status"),
        "is_valid": bool(validation.get("is_valid")),
        "reason_code": validation.get("reason_code"),
        "face_count": validation.get("face_count"),
        "message": validation.get("message"),
        "diagnostics": diagnostics,
        "thresholds": thresholds,
        "landmark_face_count": (
            (landmark_snapshot or {}).get("face_count")
            if isinstance(landmark_snapshot, dict)
            else None
        ),
        "landmark_quality_reason": (
            ((landmark_snapshot or {}).get("quality") or {}).get("reason")
            if isinstance(landmark_snapshot, dict)
            else None
        ),
        "front_capture_context_present": front_context is not None,
        "front_all_valid": front_all_valid,
        "front_message_key": front_message_key,
        "front_checklist_summary": front_checklist_summary,
        "backend_failed_after_front_ready": bool(front_all_valid is True and not validation.get("is_valid", False)),
        "front_capture_context": front_context,
    }


def infer_capture_reason_code(*, error_note: str | None, privacy_snapshot: dict | None = None) -> str:
    if isinstance(privacy_snapshot, dict):
        validation_snapshot = privacy_snapshot.get("capture_validation") or {}
        reason_code = validation_snapshot.get("reason_code")
        if reason_code:
            return str(reason_code)

    message = (error_note or "").strip()
    if not message:
        return "unknown"

    if "여러 얼굴" in message:
        return "multiple_faces_detected"
    if "얼굴이 감지되지" in message:
        return "no_face_detected"
    if "너무 멀" in message:
        return "face_too_small"
    if "흐릿" in message:
        return "too_blurry"
    if "너무 밝" in message:
        return "too_bright"
    if "너무 어두" in message:
        return "too_dark"
    if "processed" in message.lower():
        return "decode_failed"
    return "unknown"


def sanitize_original_upload(*, image: Image.Image, original_ext: str) -> tuple[bytes, str]:
    ext = original_ext.lower()
    target_format = "JPEG"
    sanitized_ext = ".jpg"

    if ext == ".png":
        target_format = "PNG"
        sanitized_ext = ".png"
    elif ext == ".webp":
        target_format = "WEBP"
        sanitized_ext = ".webp"

    buffer = io.BytesIO()
    if target_format == "JPEG":
        image.convert("RGB").save(buffer, target_format, quality=95, optimize=True)
    else:
        image.save(buffer, target_format)
    return buffer.getvalue(), sanitized_ext


def validate_capture_image(*, processed_bytes: bytes) -> dict:
    image_array = np.frombuffer(processed_bytes, dtype=np.uint8)
    decoded = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if decoded is None:
        return _base_validation_payload(
            is_valid=False,
            status="NEEDS_RETAKE",
            face_count=0,
            reason_code="decode_failed",
            message="The image could not be processed. Please take the photo again.",
        )

    gray = cv2.cvtColor(decoded, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    height, width = gray.shape[:2]
    faces = _select_candidate_faces(gray)
    face_count = len(faces)

    if brightness < MIN_BRIGHTNESS:
        return _base_validation_payload(
            is_valid=False,
            status="NEEDS_RETAKE",
            face_count=face_count,
            reason_code="too_dark",
            message="이미지가 너무 어두워 얼굴 인식이 어렵습니다. 밝은 곳에서 다시 촬영해 주세요.",
            brightness=brightness,
            sharpness=sharpness,
            image_width=width,
            image_height=height,
        )
    if brightness > MAX_BRIGHTNESS:
        return _base_validation_payload(
            is_valid=False,
            status="NEEDS_RETAKE",
            face_count=face_count,
            reason_code="too_bright",
            message="이미지가 너무 밝아 얼굴 인식이 어렵습니다. 조명을 조절한 뒤 다시 촬영해 주세요.",
            brightness=brightness,
            sharpness=sharpness,
            image_width=width,
            image_height=height,
        )
    if face_count == 0:
        return _base_validation_payload(
            is_valid=False,
            status="NEEDS_RETAKE",
            face_count=0,
            reason_code="no_face_detected",
            message="얼굴이 감지되지 않았습니다. 정면을 바라보고 다시 촬영해 주세요.",
            brightness=brightness,
            sharpness=sharpness,
            image_width=width,
            image_height=height,
        )
    if face_count > 1:
        return _base_validation_payload(
            is_valid=False,
            status="NEEDS_RETAKE",
            face_count=face_count,
            reason_code="multiple_faces_detected",
            message="여러 얼굴이 감지되었습니다. 한 명만 화면에 나오도록 다시 촬영해 주세요.",
            brightness=brightness,
            sharpness=sharpness,
            image_width=width,
            image_height=height,
        )

    x, y, face_width, face_height = faces[0]
    face_area_ratio = float(face_width * face_height) / float(width * height)
    if face_area_ratio < MIN_FACE_SIZE_RATIO:
        return _base_validation_payload(
            is_valid=False,
            status="NEEDS_RETAKE",
            face_count=face_count,
            reason_code="face_too_small",
            message="얼굴이 너무 멀어요. 카메라에 조금 더 가까이 와서 다시 촬영해 주세요.",
            brightness=brightness,
            sharpness=sharpness,
            image_width=width,
            image_height=height,
            face_area_ratio=face_area_ratio,
        )
    if sharpness < MIN_SHARPNESS:
        return _base_validation_payload(
            is_valid=False,
            status="NEEDS_RETAKE",
            face_count=face_count,
            reason_code="too_blurry",
            message="이미지가 흐릿해 정확한 분석이 어렵습니다. 잠시 멈춘 상태에서 다시 촬영해 주세요.",
            brightness=brightness,
            sharpness=sharpness,
            image_width=width,
            image_height=height,
            face_area_ratio=face_area_ratio,
        )

    return _base_validation_payload(
        is_valid=True,
        status="PENDING",
        face_count=face_count,
        reason_code="ok",
        message="얼굴 인식이 완료되었습니다. 분석을 진행합니다.",
        brightness=brightness,
        sharpness=sharpness,
        image_width=width,
        image_height=height,
        face_area_ratio=face_area_ratio,
    )
