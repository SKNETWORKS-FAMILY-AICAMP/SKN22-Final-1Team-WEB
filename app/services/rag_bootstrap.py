from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.trend_pipeline.chroma_client import create_persistent_client
from app.trend_pipeline.ncs_vectorize_chromadb import (
    COLLECTION_NAME as NCS_COLLECTION_NAME,
    INPUT_FILE as NCS_INPUT_FILE,
    build_ncs_collection,
)
from app.trend_pipeline.paths import CHROMA_NCS_DIR, CHROMA_TRENDS_DIR
from app.trend_pipeline.vectorize_chromadb import (
    COLLECTION_NAME as TREND_COLLECTION_NAME,
    FALLBACK_INPUT_FILE as TREND_FALLBACK_INPUT_FILE,
    INPUT_FILE as TREND_INPUT_FILE,
    build_collection,
)


logger = logging.getLogger(__name__)


def _collection_exists(store_dir: Path, collection_name: str) -> bool:
    if not store_dir.exists():
        return False

    try:
        client = create_persistent_client(store_dir)
        client.get_collection(collection_name)
        return True
    except Exception:
        return False


def _bootstrap_result(
    *,
    name: str,
    status: str,
    store_dir: Path,
    input_files: list[Path],
    document_count: int | None = None,
    reason: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "status": status,
        "store_dir": str(store_dir),
        "input_files": [str(path) for path in input_files],
    }
    if document_count is not None:
        payload["document_count"] = document_count
    if reason:
        payload["reason"] = reason
    return payload


def ensure_trend_store() -> dict[str, Any]:
    input_files = [TREND_INPUT_FILE, TREND_FALLBACK_INPUT_FILE]
    if _collection_exists(CHROMA_TRENDS_DIR, TREND_COLLECTION_NAME):
        return _bootstrap_result(
            name="trends",
            status="ready",
            store_dir=CHROMA_TRENDS_DIR,
            input_files=input_files,
        )

    if not any(path.exists() for path in input_files):
        return _bootstrap_result(
            name="trends",
            status="missing_input",
            store_dir=CHROMA_TRENDS_DIR,
            input_files=input_files,
            reason="No trend JSON source file was packaged with the image.",
        )

    collection = build_collection()
    return _bootstrap_result(
        name="trends",
        status="built",
        store_dir=CHROMA_TRENDS_DIR,
        input_files=input_files,
        document_count=(collection.count() if collection else 0),
    )


def ensure_ncs_store() -> dict[str, Any]:
    input_files = [NCS_INPUT_FILE]
    if _collection_exists(CHROMA_NCS_DIR, NCS_COLLECTION_NAME):
        return _bootstrap_result(
            name="ncs",
            status="ready",
            store_dir=CHROMA_NCS_DIR,
            input_files=input_files,
        )

    if not NCS_INPUT_FILE.exists():
        return _bootstrap_result(
            name="ncs",
            status="missing_input",
            store_dir=CHROMA_NCS_DIR,
            input_files=input_files,
            reason="NCS processed JSON was not packaged with the image.",
        )

    collection = build_ncs_collection()
    return _bootstrap_result(
        name="ncs",
        status="built",
        store_dir=CHROMA_NCS_DIR,
        input_files=input_files,
        document_count=(collection.count() if collection else 0),
    )


def bootstrap_rag_assets(*, include_trends: bool = True, include_ncs: bool = True) -> dict[str, Any]:
    results: list[dict[str, Any]] = []

    if include_trends:
        results.append(ensure_trend_store())
    if include_ncs:
        results.append(ensure_ncs_store())

    success = all(item["status"] in {"ready", "built"} for item in results)
    missing_inputs = [item["name"] for item in results if item["status"] == "missing_input"]
    return {
        "success": success,
        "results": results,
        "missing_inputs": missing_inputs,
    }
