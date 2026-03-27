from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .paths import CHROMA_STYLES_DIR, STYLE_SEED_FILE, ensure_directories


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


def _load_hairstyles(path: Path | None = None) -> list[dict[str, Any]]:
    source = path or STYLE_SEED_FILE
    with source.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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

    styles = _load_hairstyles()
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
