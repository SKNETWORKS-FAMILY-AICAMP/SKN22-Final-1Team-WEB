from __future__ import annotations

import io
import math
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from django.conf import settings
from PIL import Image, ImageEnhance, ImageOps


_FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
_EYE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
_SMILE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_smile.xml")


def _decode_image(processed_bytes: bytes) -> np.ndarray | None:
    try:
        pil_image = Image.open(io.BytesIO(processed_bytes))
        pil_image = ImageOps.exif_transpose(pil_image).convert("RGB")
    except Exception:
        image_array = np.frombuffer(processed_bytes, dtype=np.uint8)
        return cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    rgb_array = np.array(pil_image)
    return cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)


def _largest_face(faces) -> tuple[int, int, int, int] | None:
    if len(faces) == 0:
        return None
    return tuple(max(faces, key=lambda row: row[2] * row[3]))


def _round_point(x: float, y: float) -> dict:
    return {"x": round(float(x), 2), "y": round(float(y), 2)}


def _normalized_point(x: float, y: float, *, width: int, height: int) -> dict:
    return {
        "x": round(float(x) / float(width), 4),
        "y": round(float(y) / float(height), 4),
    }


def _point_payload(
    *,
    x: float,
    y: float,
    source: str,
    confidence: float,
    width: int,
    height: int,
) -> dict:
    return {
        "point": _round_point(x, y),
        "normalized": _normalized_point(x, y, width=width, height=height),
        "source": source,
        "confidence": round(float(confidence), 3),
    }


@lru_cache(maxsize=1)
def _load_watermark_asset() -> Image.Image | None:
    configured_path = getattr(settings, "MIRRAI_WATERMARK_IMAGE", "static/branding/mirrai_wordmark_primary.png")
    watermark_path = Path(settings.BASE_DIR) / configured_path
    if not watermark_path.exists():
        return None
    try:
        watermark = Image.open(watermark_path).convert("RGBA")
    except Exception:
        return None
    if watermark.width == 0 or watermark.height == 0:
        return None
    return watermark


def _apply_logo_watermark(image: np.ndarray) -> tuple[np.ndarray, bool, str | None, dict | None]:
    watermark = _load_watermark_asset()
    if watermark is None:
        return image, False, None, None

    height, width = image.shape[:2]
    base_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGBA))

    width_ratio = float(getattr(settings, "MIRRAI_WATERMARK_WIDTH_RATIO", 0.34))
    width_ratio = max(0.1, min(width_ratio, 0.8))
    max_logo_width = max(150, int(width * width_ratio))
    scale = max_logo_width / float(watermark.width)
    resized = watermark.resize(
        (max(1, int(round(watermark.width * scale))), max(1, int(round(watermark.height * scale)))),
        Image.LANCZOS,
    )

    opacity = float(getattr(settings, "MIRRAI_WATERMARK_OPACITY", 0.15))
    opacity = max(0.01, min(opacity, 1.0))
    angle = float(getattr(settings, "MIRRAI_WATERMARK_ANGLE", -32.0))
    spacing_x_ratio = float(getattr(settings, "MIRRAI_WATERMARK_SPACING_X_RATIO", 0.38))
    spacing_y_ratio = float(getattr(settings, "MIRRAI_WATERMARK_SPACING_Y_RATIO", 1.2))
    stagger_ratio = float(getattr(settings, "MIRRAI_WATERMARK_STAGGER_RATIO", 0.48))
    spacing_x_ratio = max(0.0, min(spacing_x_ratio, 2.0))
    spacing_y_ratio = max(0.2, min(spacing_y_ratio, 3.0))
    stagger_ratio = max(0.0, min(stagger_ratio, 1.0))

    alpha = resized.getchannel("A")
    alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
    resized.putalpha(alpha)

    pattern_width = int(width * 2.2)
    pattern_height = int(height * 2.2)
    pattern = Image.new("RGBA", (pattern_width, pattern_height), (255, 255, 255, 0))

    step_x = resized.width + int(resized.width * spacing_x_ratio)
    step_y = resized.height + int(resized.height * spacing_y_ratio)
    row_offset = int(step_x * stagger_ratio)

    row_index = 0
    for y in range(-resized.height, pattern_height + resized.height, step_y):
        offset_x = row_offset if row_index % 2 else 0
        for x in range(-resized.width + offset_x, pattern_width + resized.width, step_x):
            pattern.alpha_composite(resized, (x, y))
        row_index += 1

    rotated = pattern.rotate(angle, expand=True, resample=Image.BICUBIC)
    left = max(0, (rotated.width - width) // 2)
    top = max(0, (rotated.height - height) // 2)
    overlay = rotated.crop((left, top, left + width, top + height))

    watermarked = Image.alpha_composite(base_image, overlay)
    output = cv2.cvtColor(np.array(watermarked.convert("RGBA")), cv2.COLOR_RGBA2BGR)
    return (
        output,
        True,
        Path(getattr(settings, "MIRRAI_WATERMARK_IMAGE", "")).name,
        {
            "opacity": opacity,
            "angle": angle,
            "width_ratio": width_ratio,
            "spacing_x_ratio": spacing_x_ratio,
            "spacing_y_ratio": spacing_y_ratio,
            "stagger_ratio": stagger_ratio,
        },
    )


def _detect_eyes(roi_gray, *, face_x: int, face_y: int, face_width: int, face_height: int) -> list[tuple[float, float]]:
    detections = _EYE_CASCADE.detectMultiScale(
        roi_gray,
        scaleFactor=1.08,
        minNeighbors=5,
        minSize=(20, 20),
    )
    eyes: list[tuple[float, float]] = []
    for eye_x, eye_y, eye_width, eye_height in detections:
        center_x = face_x + eye_x + (eye_width / 2.0)
        center_y = face_y + eye_y + (eye_height / 2.0)
        if center_y > face_y + (face_height * 0.65):
            continue
        eyes.append((center_x, center_y))

    eyes.sort(key=lambda item: item[0])
    unique_eyes: list[tuple[float, float]] = []
    for center in eyes:
        if not unique_eyes:
            unique_eyes.append(center)
            continue
        previous = unique_eyes[-1]
        if abs(previous[0] - center[0]) < face_width * 0.1 and abs(previous[1] - center[1]) < face_height * 0.1:
            continue
        unique_eyes.append(center)
    return unique_eyes


def _detect_mouth_center(roi_gray, *, face_x: int, face_y: int, face_width: int, face_height: int) -> tuple[float, float] | None:
    lower_half = roi_gray[int(face_height * 0.45) :, :]
    detections = _SMILE_CASCADE.detectMultiScale(
        lower_half,
        scaleFactor=1.6,
        minNeighbors=20,
        minSize=(max(30, int(face_width * 0.2)), max(18, int(face_height * 0.08))),
    )
    if len(detections) == 0:
        return None

    mouth_x, mouth_y, mouth_width, mouth_height = max(detections, key=lambda row: row[2] * row[3])
    absolute_y = face_y + int(face_height * 0.45) + mouth_y + (mouth_height / 2.0)
    absolute_x = face_x + mouth_x + (mouth_width / 2.0)
    return absolute_x, absolute_y


def extract_landmark_snapshot(*, processed_bytes: bytes) -> dict:
    decoded = _decode_image(processed_bytes)
    if decoded is None:
        return {
            "version": "coarse-v1",
            "face_count": 0,
            "image_size": None,
            "face_bbox": None,
            "landmarks": {},
            "quality": {
                "coverage": "none",
                "detected_feature_count": 0,
                "reason": "decode_failed",
            },
        }

    height, width = decoded.shape[:2]
    gray = cv2.cvtColor(decoded, cv2.COLOR_BGR2GRAY)
    faces = _FACE_CASCADE.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(80, 80),
    )
    primary_face = _largest_face(faces)
    if primary_face is None:
        equalized = cv2.equalizeHist(gray)
        relaxed_faces = _FACE_CASCADE.detectMultiScale(
            equalized,
            scaleFactor=1.05,
            minNeighbors=4,
            minSize=(72, 72),
        )
        primary_face = _largest_face(relaxed_faces)
    if primary_face is None:
        return {
            "version": "coarse-v1",
            "face_count": 0,
            "image_size": {"width": width, "height": height},
            "face_bbox": None,
            "landmarks": {},
            "quality": {
                "coverage": "none",
                "detected_feature_count": 0,
                "reason": "no_face_detected",
            },
        }

    face_x, face_y, face_width, face_height = primary_face
    roi_gray = gray[face_y : face_y + face_height, face_x : face_x + face_width]
    eye_points = _detect_eyes(
        roi_gray,
        face_x=face_x,
        face_y=face_y,
        face_width=face_width,
        face_height=face_height,
    )
    mouth_center = _detect_mouth_center(
        roi_gray,
        face_x=face_x,
        face_y=face_y,
        face_width=face_width,
        face_height=face_height,
    )

    left_eye_source = "cascade"
    right_eye_source = "cascade"
    left_eye_confidence = 0.82
    right_eye_confidence = 0.82
    if len(eye_points) >= 2:
        left_eye = eye_points[0]
        right_eye = eye_points[-1]
    else:
        left_eye = (face_x + (face_width * 0.32), face_y + (face_height * 0.38))
        right_eye = (face_x + (face_width * 0.68), face_y + (face_height * 0.38))
        if len(eye_points) == 1:
            detected_eye = eye_points[0]
            if detected_eye[0] <= face_x + (face_width / 2.0):
                left_eye = detected_eye
                left_eye_source = "cascade"
                left_eye_confidence = 0.82
                right_eye_source = "heuristic"
                right_eye_confidence = 0.42
            else:
                right_eye = detected_eye
                right_eye_source = "cascade"
                right_eye_confidence = 0.82
                left_eye_source = "heuristic"
                left_eye_confidence = 0.42
        else:
            left_eye_source = "heuristic"
            right_eye_source = "heuristic"
            left_eye_confidence = 0.35
            right_eye_confidence = 0.35

    if mouth_center is None:
        mouth_center = (face_x + (face_width / 2.0), face_y + (face_height * 0.75))
        mouth_source = "heuristic"
        mouth_confidence = 0.38
    else:
        mouth_source = "cascade"
        mouth_confidence = 0.7

    nose_tip_x = (left_eye[0] + right_eye[0] + (mouth_center[0] * 1.2)) / 3.2
    nose_tip_y = (left_eye[1] + right_eye[1] + (mouth_center[1] * 1.4)) / 3.4
    chin_center = (face_x + (face_width / 2.0), face_y + (face_height * 0.94))

    eye_distance = math.dist(left_eye, right_eye)
    eye_line_angle_deg = math.degrees(math.atan2(right_eye[1] - left_eye[1], right_eye[0] - left_eye[0]))

    landmarks = {
        "left_eye": _point_payload(
            x=left_eye[0],
            y=left_eye[1],
            source=left_eye_source,
            confidence=left_eye_confidence,
            width=width,
            height=height,
        ),
        "right_eye": _point_payload(
            x=right_eye[0],
            y=right_eye[1],
            source=right_eye_source,
            confidence=right_eye_confidence,
            width=width,
            height=height,
        ),
        "nose_tip": _point_payload(
            x=nose_tip_x,
            y=nose_tip_y,
            source="derived",
            confidence=0.56,
            width=width,
            height=height,
        ),
        "mouth_center": _point_payload(
            x=mouth_center[0],
            y=mouth_center[1],
            source=mouth_source,
            confidence=mouth_confidence,
            width=width,
            height=height,
        ),
        "chin_center": _point_payload(
            x=chin_center[0],
            y=chin_center[1],
            source="derived",
            confidence=0.5,
            width=width,
            height=height,
        ),
    }

    return {
        "version": "coarse-v1",
        "face_count": len(faces),
        "image_size": {"width": width, "height": height},
        "face_bbox": {
            "x": int(face_x),
            "y": int(face_y),
            "width": int(face_width),
            "height": int(face_height),
            "normalized": {
                "x": round(float(face_x) / float(width), 4),
                "y": round(float(face_y) / float(height), 4),
                "width": round(float(face_width) / float(width), 4),
                "height": round(float(face_height) / float(height), 4),
            },
        },
        "landmarks": landmarks,
        "quality": {
            "coverage": "coarse",
            "detected_feature_count": len(landmarks),
            "eye_line_angle_deg": round(float(eye_line_angle_deg), 2),
            "eye_distance_px": round(float(eye_distance), 2),
        },
    }


def build_deidentified_capture(*, processed_bytes: bytes, landmark_snapshot: dict | None = None) -> tuple[bytes | None, dict]:
    decoded = _decode_image(processed_bytes)
    if decoded is None:
        return None, {
            "metadata_removed": True,
            "deidentification_applied": False,
            "method": "metadata_only",
            "reason": "decode_failed",
        }

    snapshot = landmark_snapshot or extract_landmark_snapshot(processed_bytes=processed_bytes)
    face_bbox = snapshot.get("face_bbox") or {}
    if not face_bbox:
        return None, {
            "metadata_removed": True,
            "deidentification_applied": False,
            "method": "metadata_only",
            "reason": "face_bbox_missing",
        }

    height, width = decoded.shape[:2]
    face_x = int(face_bbox["x"])
    face_y = int(face_bbox["y"])
    face_width = int(face_bbox["width"])
    face_height = int(face_bbox["height"])

    padding_x = max(10, int(face_width * 0.12))
    padding_y = max(10, int(face_height * 0.16))
    start_x = max(0, face_x - padding_x)
    end_x = min(width, face_x + face_width + padding_x)
    start_y = max(0, face_y - padding_y)
    end_y = min(height, face_y + face_height + padding_y)

    face_region = decoded[start_y:end_y, start_x:end_x]
    downsampled_width = max(18, (end_x - start_x) // 10)
    downsampled_height = max(18, (end_y - start_y) // 10)
    pixelated = cv2.resize(face_region, (downsampled_width, downsampled_height), interpolation=cv2.INTER_LINEAR)
    pixelated = cv2.resize(pixelated, (end_x - start_x, end_y - start_y), interpolation=cv2.INTER_NEAREST)
    decoded[start_y:end_y, start_x:end_x] = pixelated

    landmarks = snapshot.get("landmarks") or {}
    left_eye = (landmarks.get("left_eye") or {}).get("point")
    right_eye = (landmarks.get("right_eye") or {}).get("point")
    eye_bar_applied = False
    if left_eye and right_eye:
        eye_bar_height = max(8, int(face_height * 0.12))
        bar_padding = max(6, int(face_width * 0.06))
        bar_start_x = max(0, int(min(left_eye["x"], right_eye["x"])) - bar_padding)
        bar_end_x = min(width, int(max(left_eye["x"], right_eye["x"])) + bar_padding)
        bar_center_y = int((left_eye["y"] + right_eye["y"]) / 2.0)
        bar_start_y = max(0, bar_center_y - (eye_bar_height // 2))
        bar_end_y = min(height, bar_center_y + (eye_bar_height // 2))
        cv2.rectangle(decoded, (bar_start_x, bar_start_y), (bar_end_x, bar_end_y), (0, 0, 0), thickness=-1)
        eye_bar_applied = True

    decoded, watermark_applied, watermark_asset, watermark_config = _apply_logo_watermark(decoded)

    success, encoded = cv2.imencode(".jpg", decoded, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if not success:
        return None, {
            "metadata_removed": True,
            "deidentification_applied": False,
            "method": "metadata_only",
            "reason": "encode_failed",
        }

    privacy_snapshot = {
        "metadata_removed": True,
        "deidentification_applied": True,
        "method": "pixelate_face_region",
        "eye_bar_applied": eye_bar_applied,
        "watermark_applied": watermark_applied,
        "watermark_mode": "image" if watermark_applied else None,
        "watermark_asset": watermark_asset,
        "watermark_config": watermark_config if watermark_applied else None,
        "masked_region": {
            "x": start_x,
            "y": start_y,
            "width": end_x - start_x,
            "height": end_y - start_y,
        },
        "landmark_keys": sorted(list(landmarks.keys())),
    }
    return encoded.tobytes(), privacy_snapshot
