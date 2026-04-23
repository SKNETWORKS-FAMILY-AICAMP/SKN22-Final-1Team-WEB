from __future__ import annotations

import gc
import json
import shutil
import sys
import time
from typing import Any

import chromadb
from chromadb.errors import NotFoundError

from .chroma_client import create_persistent_client
from .paths import CHROMA_NCS_DIR, NCS_PROCESSED_DIR, ensure_directories


INPUT_FILE = NCS_PROCESSED_DIR / "ncs_rag_ready.json"
COLLECTION_NAME = "hair_ncs_manuals"


def load_data() -> list[dict[str, Any]]:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE}")

    with INPUT_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(f"Invalid JSON structure: {INPUT_FILE}")
    return [item for item in data if isinstance(item, dict)]


def _should_reset_incompatible_store(exc: Exception) -> bool:
    return isinstance(exc, KeyError) and exc.args == ("_type",)


def _is_store_busy_error(exc: Exception) -> bool:
    return isinstance(exc, PermissionError) and "chroma.sqlite3" in str(exc).lower()


def _raise_store_busy_error(*, exc: Exception) -> None:
    raise PermissionError(
        f"Chroma NCS store is busy at '{CHROMA_NCS_DIR}'. "
        "Stop any Django/FastAPI/process using this store, then rerun rebuild_ncs."
    ) from exc


def _reset_ncs_store(*, stale_client: Any | None = None) -> None:
    if stale_client is not None:
        close = getattr(stale_client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
    stale_client = None
    gc.collect()
    time.sleep(0.1)

    if CHROMA_NCS_DIR.exists():
        shutil.rmtree(CHROMA_NCS_DIR)
    CHROMA_NCS_DIR.mkdir(parents=True, exist_ok=True)


def build_ncs_collection() -> chromadb.api.models.Collection.Collection:
    ensure_directories()
    data = load_data()
    print(f"Loaded {len(data)} NCS records.")

    try:
        client = create_persistent_client(CHROMA_NCS_DIR)
        try:
            client.delete_collection(COLLECTION_NAME)
            print(f"Deleted existing collection '{COLLECTION_NAME}'.")
        except (ValueError, NotFoundError):
            pass
        except Exception as exc:
            if not _should_reset_incompatible_store(exc):
                raise
            print(
                "[chroma] incompatible existing NCS store detected; "
                "resetting local store before rebuild."
            )
            stale_client = client
            client = None
            _reset_ncs_store(stale_client=stale_client)
            client = create_persistent_client(CHROMA_NCS_DIR)

        collection = client.create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "NCS hairstyle manual RAG data maintained inside final_web backend"},
        )

        batch_size = 200
        for start in range(0, len(data), batch_size):
            batch = data[start : start + batch_size]
            ids: list[str] = []
            documents: list[str] = []
            metadatas: list[dict[str, Any]] = []

            for offset, item in enumerate(batch):
                idx = start + offset
                ids.append(f"ncs_{idx:05d}")
                documents.append(str(item.get("search_text") or ""))
                metadatas.append(
                    {
                        "source_id": str(item.get("source_id") or ""),
                        "canonical_name": str(item.get("canonical_name") or ""),
                        "display_title": str(item.get("display_title") or ""),
                        "category": str(item.get("category") or ""),
                        "service_type": ", ".join(item.get("service_type", [])),
                        "target_conditions": ", ".join(item.get("target_conditions", [])),
                        "tools": ", ".join(item.get("tools", [])),
                        "steps": " | ".join(item.get("steps", [])),
                        "cautions": " | ".join(item.get("cautions", [])),
                        "summary": str(item.get("summary") or ""),
                        "stylist_answer": str(item.get("stylist_answer") or ""),
                        "source_document_name": str(item.get("source_document_name") or ""),
                        "source_page": str(item.get("source_page") or ""),
                        "source_alias_names": ", ".join(item.get("source_alias_names", [])),
                        "source": str(item.get("source") or ""),
                    }
                )

            collection.add(ids=ids, documents=documents, metadatas=metadatas)
            print(f"  inserted [{start + len(batch)}/{len(data)}]")
    except PermissionError as exc:
        if _is_store_busy_error(exc):
            _raise_store_busy_error(exc=exc)
        raise

    print("\n====== NCS vectorization complete ======")
    print(f"collection: {COLLECTION_NAME} ({collection.count()} docs)")
    print(f"store path: {CHROMA_NCS_DIR}")
    return collection


def query_test(collection: chromadb.api.models.Collection.Collection, query_text: str, n_results: int = 5) -> None:
    del collection
    from .ncs_rag_query import retrieve

    results = retrieve(query_text, n_results=n_results)
    print(_console_safe(f'\nquery: "{query_text}"'))
    print(_console_safe("-" * 60))
    for index, metadata in enumerate(results, start=1):
        print(_console_safe(f"  [{index}] {metadata['title']}"))
        print(_console_safe(f"      category: {metadata['category']} | service: {metadata['service_type']}"))
        print(_console_safe(f"      source: {metadata['source_document_name']} p.{metadata['source_page']}"))
        print()


def main() -> None:
    collection = build_ncs_collection()
    client = create_persistent_client(CHROMA_NCS_DIR)
    collection = client.get_collection(COLLECTION_NAME)
    query_test(collection, "손상모 클리닉 시술 순서")
    query_test(collection, "단발 커트 기본 섹션")
    query_test(collection, "염색 후 마무리 주의사항")


def _console_safe(value: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return value.encode(encoding, errors="replace").decode(encoding, errors="replace")


if __name__ == "__main__":
    main()
