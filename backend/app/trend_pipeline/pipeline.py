from __future__ import annotations

import logging
import time
from typing import Any


logger = logging.getLogger(__name__)

VALID_STEPS = ("crawl", "refine", "llm_refine", "vectorize", "rebuild_styles", "analyze")
DEFAULT_REFRESH_STEPS = ("crawl", "refine", "llm_refine", "vectorize", "rebuild_styles")


def refresh_trends(steps: list[str] | None = None) -> dict[str, Any]:
    if steps is None:
        steps = list(DEFAULT_REFRESH_STEPS)

    invalid = [step for step in steps if step not in VALID_STEPS]
    if invalid:
        return {"error": f"Unsupported step(s): {invalid}. Valid steps: {VALID_STEPS}"}

    results: dict[str, Any] = {
        "steps_requested": steps,
        "steps_completed": [],
        "steps_failed": [],
        "details": {},
    }
    started_at = time.time()

    for step in steps:
        step_started_at = time.time()
        logger.info("[refresh_trends] === %s started ===", step)
        try:
            detail = _run_step(step)
            elapsed = round(time.time() - step_started_at, 2)
            results["steps_completed"].append(step)
            results["details"][step] = {"status": "ok", "elapsed_seconds": elapsed, **detail}
            logger.info("[refresh_trends] === %s completed (%ss) ===", step, elapsed)
        except Exception as exc:
            elapsed = round(time.time() - step_started_at, 2)
            results["steps_failed"].append(step)
            results["details"][step] = {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_seconds": elapsed,
            }
            logger.exception("[refresh_trends] === %s failed ===", step)

    results["total_elapsed_seconds"] = round(time.time() - started_at, 2)
    results["success"] = len(results["steps_failed"]) == 0
    return results


def _run_step(step: str) -> dict[str, Any]:
    if step == "crawl":
        from .universal_crawler import UniversalCrawler

        UniversalCrawler().crawl()
        return {"description": "Trend crawl completed."}

    if step == "refine":
        from .data_refiner import DataRefiner

        DataRefiner().refine()
        return {"description": "Refined raw trend data."}

    if step == "llm_refine":
        from .llm_refiner import LLMRefiner

        LLMRefiner().refine_with_llm()
        return {"description": "Completed LLM-based normalization."}

    if step == "vectorize":
        from .vectorize_chromadb import build_collection

        collection = build_collection()
        return {
            "description": "Updated ChromaDB trend vectors.",
            "document_count": (collection.count() if collection else 0),
        }

    if step == "rebuild_styles":
        from .style_collection import build_style_collection, sync_seed_styles_to_db

        collection = build_style_collection()
        sync_result = sync_seed_styles_to_db()
        return {
            "description": "Rebuilt style collection and synced backend style records.",
            "style_count": (collection.count() if collection else 0),
            "db_sync": sync_result,
        }

    if step == "analyze":
        from .analyze_trends import KeywordAnalyzer

        KeywordAnalyzer().analyze_and_visualize()
        return {"description": "Trend keyword analysis completed."}

    return {}
