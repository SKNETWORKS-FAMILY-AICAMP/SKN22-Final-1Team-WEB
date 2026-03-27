from __future__ import annotations

from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
RAG_DIR = DATA_DIR / "rag"
RAW_DATA_DIR = RAG_DIR / "raw"
TREND_RAW_DIR = RAW_DATA_DIR / "trends"
PROCESSED_DATA_DIR = RAG_DIR / "processed"
TREND_PROCESSED_DIR = PROCESSED_DATA_DIR / "trends"
ANALYSIS_DIR = RAG_DIR / "analysis"
RAG_STORE_DIR = RAG_DIR / "stores"
CHROMA_TRENDS_DIR = RAG_STORE_DIR / "chromadb_trends"
CHROMA_NCS_DIR = RAG_STORE_DIR / "chromadb_ncs"
CHROMA_STYLES_DIR = RAG_STORE_DIR / "chromadb_styles"
STYLE_SEED_FILE = DATA_DIR / "trend_hairstyles.json"


def ensure_directories() -> None:
    for path in (
        DATA_DIR,
        RAG_DIR,
        RAW_DATA_DIR,
        TREND_RAW_DIR,
        PROCESSED_DATA_DIR,
        TREND_PROCESSED_DIR,
        ANALYSIS_DIR,
        RAG_STORE_DIR,
        CHROMA_TRENDS_DIR,
        CHROMA_NCS_DIR,
        CHROMA_STYLES_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
