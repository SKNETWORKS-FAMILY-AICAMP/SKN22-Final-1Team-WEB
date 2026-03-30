from __future__ import annotations

import logging
import json
import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .paths import CHROMA_STYLES_DIR, STYLE_SEED_FILE, ensure_directories


logger = logging.getLogger(__name__)


FACE_SHAPES = ("oval", "round", "square", "heart", "oblong")
LENGTHS = ("short", "medium", "long")
MOODS = ("natural", "trendy", "classic", "edgy", "cute")
HAIR_TYPES = ("straight", "wavy", "curly")
COLOR_TEMPS = ("warm", "cool", "neutral")
BUDGETS = ("low", "medium", "high")

W_FACE = 0.40
W_GOLDEN = 0.20
W_PREF = 0.40

VEC_DIM = 23
_IDX_FACE = 0
_IDX_GOLDEN = 5
_IDX_LENGTH = 6
_IDX_MOOD = 9
_IDX_HAIR = 14
_IDX_COLOR = 17
_IDX_BUDGET = 20


def _one_hot(value: str, categories: Sequence[str]) -> np.ndarray:
    vector = np.zeros(len(categories), dtype=np.float32)
    if value in categories:
        vector[categories.index(value)] = 1.0
    return vector


def _multi_hot(values: Sequence[str], categories: Sequence[str]) -> np.ndarray:
    vector = np.zeros(len(categories), dtype=np.float32)
    for value in values:
        if value in categories:
            vector[categories.index(value)] = 1.0
    norm = np.linalg.norm(vector)
    if norm > 1e-6:
        vector = vector / norm
    return vector


def encode_style_vector(style: dict[str, Any]) -> np.ndarray:
    vector = np.zeros(VEC_DIM, dtype=np.float32)
    vector[_IDX_FACE:_IDX_FACE + len(FACE_SHAPES)] = _multi_hot(style.get("face_shapes", []), FACE_SHAPES)
    vector[_IDX_GOLDEN] = 0.5
    vector[_IDX_LENGTH:_IDX_LENGTH + len(LENGTHS)] = _one_hot(style.get("length", "medium"), LENGTHS)
    vector[_IDX_MOOD:_IDX_MOOD + len(MOODS)] = _multi_hot(style.get("mood", []), MOODS)
    vector[_IDX_HAIR:_IDX_HAIR + len(HAIR_TYPES)] = _multi_hot(style.get("hair_types", []), HAIR_TYPES)
    vector[_IDX_COLOR:_IDX_COLOR + len(COLOR_TEMPS)] = _one_hot(style.get("color_temp", "neutral"), COLOR_TEMPS)
    vector[_IDX_BUDGET:_IDX_BUDGET + len(BUDGETS)] = _one_hot(style.get("maintenance", "medium"), BUDGETS)
    return vector


def _apply_weight_scaling(vector: np.ndarray) -> np.ndarray:
    scaled = vector.copy()
    scaled[_IDX_FACE:_IDX_FACE + len(FACE_SHAPES)] *= math.sqrt(W_FACE)
    scaled[_IDX_GOLDEN] *= math.sqrt(W_GOLDEN)
    pref_scale = math.sqrt(W_PREF)
    scaled[_IDX_LENGTH:_IDX_LENGTH + len(LENGTHS)] *= pref_scale
    scaled[_IDX_MOOD:_IDX_MOOD + len(MOODS)] *= pref_scale
    scaled[_IDX_HAIR:_IDX_HAIR + len(HAIR_TYPES)] *= pref_scale
    scaled[_IDX_COLOR:_IDX_COLOR + len(COLOR_TEMPS)] *= pref_scale
    scaled[_IDX_BUDGET:_IDX_BUDGET + len(BUDGETS)] *= pref_scale
    return scaled


def load_hairstyles(path: Path | None = None) -> list[dict[str, Any]]:
    source = path or STYLE_SEED_FILE
    with source.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _style_vibe(style: dict[str, Any]) -> str:
    moods = style.get("mood") or []
    if moods:
        return str(moods[0]).title()
    return "Trendy"


def _normalized_style_name(style: dict[str, Any]) -> str:
    return str(style.get("style_name") or "").strip()


def _dedupe_styles_by_name(styles: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    deduped: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    duplicate_count = 0
    skipped_count = 0

    for style in styles:
        style_name = _normalized_style_name(style)
        if not style_name:
            skipped_count += 1
            continue
        if style_name in seen_names:
            duplicate_count += 1
            continue
        seen_names.add(style_name)
        deduped.append(style)

    return deduped, duplicate_count, skipped_count


def sync_seed_styles_to_db(styles: list[dict[str, Any]] | None = None) -> dict[str, int]:
    from app.models_django import Style

    source_styles = styles or load_hairstyles()
    normalized_styles, duplicate_count, skipped_count = _dedupe_styles_by_name(source_styles)
    created_count = 0
    updated_count = 0

    for style in normalized_styles:
        defaults = {
            "vibe": _style_vibe(style),
            "description": str(style.get("description") or "").strip(),
        }
        style_name = _normalized_style_name(style)
        record = Style.objects.filter(name=style_name).order_by("id").first()
        if record is None:
            record = Style.objects.create(name=style_name, **defaults)
            created = True
        else:
            created = False
            changed = False
            for field, value in defaults.items():
                if getattr(record, field) != value:
                    setattr(record, field, value)
                    changed = True
            if changed:
                record.save(update_fields=list(defaults.keys()))

        if created:
            created_count += 1
        else:
            updated_count += 1

        image_url = str(style.get("image_url") or style.get("sample_image_url") or "").strip()
        if image_url and record.image_url != image_url:
            record.image_url = image_url
            record.save(update_fields=["image_url"])

    logger.info(
        "[trend_style_sync] seed styles synced: total=%s created=%s updated=%s duplicate=%s skipped=%s",
        len(normalized_styles),
        created_count,
        updated_count,
        duplicate_count,
        skipped_count,
    )

    return {
        "style_count": len(normalized_styles),
        "created_count": created_count,
        "updated_count": updated_count,
        "duplicate_count": duplicate_count,
        "skipped_count": skipped_count,
    }


def build_style_collection(client=None):
    import chromadb

    ensure_directories()
    if client is None:
        client = chromadb.PersistentClient(path=str(CHROMA_STYLES_DIR))

    try:
        client.delete_collection("hairstyle_features")
    except Exception:
        pass

    collection = client.create_collection(
        name="hairstyle_features",
        metadata={
            "description": "Hairstyle feature vectors for recommendation",
            "hnsw:space": "cosine",
        },
    )

    styles = load_hairstyles()
    ids: list[str] = []
    embeddings: list[list[float]] = []
    metadatas: list[dict[str, Any]] = []
    documents: list[str] = []

    for style in styles:
        scaled = _apply_weight_scaling(encode_style_vector(style))
        ids.append(str(style["id"]))
        embeddings.append(scaled.tolist())
        metadatas.append(
            {
                "style_name": style["style_name"],
                "description": style["description"],
                "face_shapes": ",".join(style.get("face_shapes", [])),
                "length": style.get("length", "medium"),
                "mood": ",".join(style.get("mood", [])),
                "hair_types": ",".join(style.get("hair_types", [])),
                "maintenance": style.get("maintenance", "medium"),
                "popularity_score": style.get("popularity_score", 0.5),
                "freshness_score": style.get("freshness_score", 0.5),
                "sd_positive": style.get("sd_positive", ""),
                "sd_negative": style.get("sd_negative", ""),
                "sd_guidance": style.get("sd_guidance", 8.5),
            }
        )
        documents.append(
            f"{style['style_name']}: {style['description']} "
            f"Keywords: {', '.join(style.get('keywords', []))}"
        )

    collection.add(
        ids=ids,
        embeddings=embeddings,
        metadatas=metadatas,
        documents=documents,
    )
    return collection
