from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


PROCESSING_STATUSES = {"PROCESSING", "PENDING", "QUEUED", "STARTED"}


@dataclass(frozen=True)
class RecommendationWaitPolicy:
    timeout_seconds: float
    interval_seconds: float


@dataclass(frozen=True)
class RecommendationRuntimeState:
    latest_capture_attempt: Any
    latest_survey: Any
    latest_capture: Any
    latest_analysis: Any
    legacy_items: list[dict]


@dataclass(frozen=True)
class PreparedRecommendationAssets:
    items: list[dict]
    batch_id: str | None
    item_count: int
    ready_count: int
    primary_simulation_count: int
    sample_only_count: int
    is_ready: bool
    has_pending_assets: bool


def build_runtime_state(
    *,
    latest_capture_attempt: Any,
    latest_survey: Any,
    latest_capture: Any,
    latest_analysis: Any,
    legacy_items: list[dict] | None,
) -> RecommendationRuntimeState:
    return RecommendationRuntimeState(
        latest_capture_attempt=latest_capture_attempt,
        latest_survey=latest_survey,
        latest_capture=latest_capture,
        latest_analysis=latest_analysis,
        legacy_items=list(legacy_items or []),
    )


def coerce_identifier(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def analysis_identifier(analysis: Any) -> str | None:
    return coerce_identifier(
        getattr(analysis, "id", None)
        or getattr(analysis, "analysis_id", None)
    )


def normalize_status(value: Any) -> str:
    return str(value or "").strip().upper()


def is_processing_status(value: Any) -> bool:
    return normalize_status(value) in PROCESSING_STATUSES


def runtime_requires_wait_for_recommendations(state: RecommendationRuntimeState) -> bool:
    if is_processing_status(getattr(state.latest_capture_attempt, "status", None)):
        return True
    if is_processing_status(getattr(state.latest_capture, "status", None)):
        return True
    if is_processing_status(getattr(state.latest_analysis, "status", None)):
        return True

    if state.latest_analysis is not None and not getattr(state.latest_analysis, "image_url", None):
        return is_processing_status(getattr(state.latest_capture, "status", None))

    return False


def filter_items_for_current_analysis(*, items: list[dict], latest_analysis: Any) -> list[dict]:
    if not items:
        return []

    target_analysis_id = analysis_identifier(latest_analysis)
    if not target_analysis_id:
        return [dict(item) for item in items]

    exact_matches = [
        dict(item)
        for item in items
        if coerce_identifier(item.get("analysis_id")) == target_analysis_id
    ]
    if exact_matches:
        return exact_matches

    unscoped_items = [
        dict(item)
        for item in items
        if coerce_identifier(item.get("analysis_id")) is None
    ]
    return unscoped_items


def prepare_recommendation_assets(
    *,
    items: list[dict],
    latest_analysis: Any,
    persist_reference: Callable[[str | None], str | None],
) -> PreparedRecommendationAssets:
    scoped_items = filter_items_for_current_analysis(items=items, latest_analysis=latest_analysis)
    prepared_items: list[dict] = []

    for item in scoped_items:
        normalized = dict(item)
        simulation_candidate = (
            normalized.get("simulation_image_url")
            or normalized.get("synthetic_image_url")
        )
        persisted_simulation = persist_reference(simulation_candidate)
        has_primary_simulation = bool(coerce_identifier(persisted_simulation))
        has_sample_reference = bool(coerce_identifier(normalized.get("sample_image_url")))

        if has_primary_simulation:
            normalized["simulation_image_url"] = persisted_simulation
            normalized["synthetic_image_url"] = persisted_simulation
        else:
            normalized["simulation_image_url"] = None
            normalized["synthetic_image_url"] = None

        normalized["has_primary_simulation"] = has_primary_simulation
        normalized["has_sample_reference"] = has_sample_reference
        prepared_items.append(normalized)

    item_count = len(prepared_items)
    ready_count = sum(1 for item in prepared_items if item["has_primary_simulation"])
    sample_only_count = sum(
        1
        for item in prepared_items
        if not item["has_primary_simulation"] and item["has_sample_reference"]
    )
    is_ready = item_count > 0 and ready_count == item_count
    batch_id = next(
        (
            coerce_identifier(item.get("batch_id"))
            for item in prepared_items
            if coerce_identifier(item.get("batch_id"))
        ),
        None,
    )

    return PreparedRecommendationAssets(
        items=prepared_items,
        batch_id=batch_id,
        item_count=item_count,
        ready_count=ready_count,
        primary_simulation_count=ready_count,
        sample_only_count=sample_only_count,
        is_ready=is_ready,
        has_pending_assets=item_count > 0 and not is_ready,
    )


def wait_for_runtime_state(
    *,
    load_state: Callable[[], RecommendationRuntimeState],
    should_wait: Callable[[RecommendationRuntimeState], bool],
    clock,
    wait_policy: RecommendationWaitPolicy,
) -> tuple[RecommendationRuntimeState, bool]:
    state = load_state()
    if not should_wait(state):
        return state, False

    started_at = clock.monotonic()
    while should_wait(state):
        if (clock.monotonic() - started_at) >= wait_policy.timeout_seconds:
            return state, True
        clock.sleep(wait_policy.interval_seconds)
        state = load_state()

    return state, False
