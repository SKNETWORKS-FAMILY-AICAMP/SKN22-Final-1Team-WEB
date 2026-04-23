from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.config import Settings


_CHROMA_SETTINGS = Settings(anonymized_telemetry=False)


def create_persistent_client(path: str | Path):
    return chromadb.PersistentClient(
        path=str(path),
        settings=_CHROMA_SETTINGS,
    )
