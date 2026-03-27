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
        return {"error": f"잘못된 단계: {invalid}. 가능한 값: {VALID_STEPS}"}

    results: dict[str, Any] = {
        "steps_requested": steps,
        "steps_completed": [],
        "steps_failed": [],
        "details": {},
    }
    started_at = time.time()

    for step in steps:
        step_started_at = time.time()
        logger.info("[refresh_trends] === %s 시작 ===", step)
        try:
            detail = _run_step(step)
            elapsed = round(time.time() - step_started_at, 2)
            results["steps_completed"].append(step)
            results["details"][step] = {"status": "ok", "elapsed_seconds": elapsed, **detail}
            logger.info("[refresh_trends] === %s 완료 (%ss) ===", step, elapsed)
        except Exception as exc:
            elapsed = round(time.time() - step_started_at, 2)
            results["steps_failed"].append(step)
            results["details"][step] = {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_seconds": elapsed,
            }
            logger.exception("[refresh_trends] === %s 실패 ===", step)

    results["total_elapsed_seconds"] = round(time.time() - started_at, 2)
    results["success"] = len(results["steps_failed"]) == 0
    return results


def _run_step(step: str) -> dict[str, Any]:
    if step == "crawl":
        from .universal_crawler import UniversalCrawler

        UniversalCrawler().crawl()
        return {"description": "트렌드 웹 크롤링 완료"}

    if step == "refine":
        from .data_refiner import DataRefiner

        DataRefiner().refine()
        return {"description": "크롤링 데이터 정제 완료"}

    if step == "llm_refine":
        from .llm_refiner import LLMRefiner

        LLMRefiner().refine_with_llm()
        return {"description": "LLM 기반 정제 완료"}

    if step == "vectorize":
        from .vectorize_chromadb import build_collection

        collection = build_collection()
        return {
            "description": "ChromaDB 트렌드 벡터DB 갱신 완료",
            "document_count": (collection.count() if collection else 0),
        }

    if step == "rebuild_styles":
        from .style_collection import build_style_collection

        collection = build_style_collection()
        return {
            "description": "스타일 추천 컬렉션 리빌드 완료",
            "style_count": (collection.count() if collection else 0),
        }

    if step == "analyze":
        from .analyze_trends import KeywordAnalyzer

        KeywordAnalyzer().analyze_and_visualize()
        return {"description": "키워드 분석 완료"}

    return {}
