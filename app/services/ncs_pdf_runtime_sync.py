from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


NCS_RUNTIME_TARGET_DIR = Path(__file__).resolve().parents[2] / "data" / "rag" / "sources" / "ncs"


def _normalize_source_dir(source_dir: str | Path) -> Path:
    return Path(str(source_dir or "")).expanduser().resolve()


def _pdf_files(source_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    )


def sync_ncs_source_pdfs(
    *,
    source_dir: str | Path,
    target_dir: str | Path = NCS_RUNTIME_TARGET_DIR,
    overwrite: bool = False,
) -> dict[str, Any]:
    normalized_source_dir = _normalize_source_dir(source_dir)
    normalized_target_dir = Path(str(target_dir or NCS_RUNTIME_TARGET_DIR)).resolve()

    if not normalized_source_dir.exists():
        return {
            "success": False,
            "status": "missing_source_dir",
            "source_dir": str(normalized_source_dir),
            "target_dir": str(normalized_target_dir),
            "copied": [],
            "skipped": [],
            "reason": "Source directory does not exist.",
        }

    if not normalized_source_dir.is_dir():
        return {
            "success": False,
            "status": "invalid_source_dir",
            "source_dir": str(normalized_source_dir),
            "target_dir": str(normalized_target_dir),
            "copied": [],
            "skipped": [],
            "reason": "Source path is not a directory.",
        }

    pdf_files = _pdf_files(normalized_source_dir)
    if not pdf_files:
        return {
            "success": False,
            "status": "missing_pdf_files",
            "source_dir": str(normalized_source_dir),
            "target_dir": str(normalized_target_dir),
            "copied": [],
            "skipped": [],
            "reason": "No PDF files were found in the source directory.",
        }

    normalized_target_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    skipped: list[str] = []
    for source_path in pdf_files:
        destination_path = normalized_target_dir / source_path.name
        if destination_path.exists() and not overwrite:
            skipped.append(source_path.name)
            continue
        shutil.copy2(source_path, destination_path)
        copied.append(source_path.name)

    return {
        "success": True,
        "status": "synced",
        "source_dir": str(normalized_source_dir),
        "target_dir": str(normalized_target_dir),
        "copied": copied,
        "skipped": skipped,
        "source_count": len(pdf_files),
    }
