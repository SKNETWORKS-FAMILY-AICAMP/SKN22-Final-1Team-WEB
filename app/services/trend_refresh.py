from __future__ import annotations

import base64
import io
import json
import tarfile
import time
from pathlib import Path
from typing import Any, Iterable

import requests
from django.conf import settings

from app.trend_pipeline.paths import RAG_STORE_DIR
from app.trend_pipeline.pipeline import DEFAULT_REFRESH_STEPS, VALID_STEPS, refresh_trends


FAILED_RUNPOD_STATUSES = {"FAILED", "CANCELLED", "TIMED_OUT"}


class TrendRefreshError(RuntimeError):
    pass


def parse_refresh_steps(value: str | Iterable[str] | None) -> list[str] | None:
    if value is None:
        return None

    if isinstance(value, str):
        raw_steps = [item.strip() for item in value.split(",")]
    else:
        raw_steps = [str(item).strip() for item in value]

    steps = [step for step in raw_steps if step]
    if not steps:
        return None

    invalid = [step for step in steps if step not in VALID_STEPS]
    if invalid:
        raise TrendRefreshError(
            f"Unsupported refresh step(s): {', '.join(invalid)}. "
            f"Valid steps: {', '.join(VALID_STEPS)}"
        )
    return steps


def trigger_runpod_trend_refresh(
    *,
    steps: str | Iterable[str] | None = None,
    endpoint_id: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    sync: bool = True,
    wait: bool = True,
    timeout: int = 1800,
    poll_interval: float = 5.0,
    dry_run: bool = False,
) -> dict[str, Any]:
    normalized_steps = parse_refresh_steps(steps)
    request_input: dict[str, Any] = {"action": "refresh_trends"}
    if normalized_steps is not None:
        request_input["steps"] = normalized_steps

    result: dict[str, Any] = {
        "request_mode": "runpod_pipeline",
        "request_input": request_input,
    }
    if dry_run:
        result["dry_run"] = True
        return result

    runpod_response = _submit_runpod_job(
        request_input=request_input,
        endpoint_id=endpoint_id,
        api_key=api_key,
        base_url=base_url,
        sync=sync,
        wait=wait,
        timeout=timeout,
        poll_interval=poll_interval,
    )
    result["runpod_response"] = runpod_response
    return result


def trigger_runpod_trend_refresh_with_archive(
    *,
    endpoint_id: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    sync: bool = True,
    wait: bool = True,
    timeout: int = 1800,
    poll_interval: float = 5.0,
    build_locally: bool = False,
    steps: str | Iterable[str] | None = None,
    include_ncs: bool = True,
    include_styles: bool = True,
    dry_run: bool = False,
    stores_root: str | Path | None = None,
) -> dict[str, Any]:
    local_pipeline_result = None
    if build_locally:
        local_pipeline_result = run_local_refresh_trends_pipeline(steps=steps)

    archive_bytes, included_collections = build_chromadb_archive(
        include_ncs=include_ncs,
        include_styles=include_styles,
        stores_root=stores_root,
    )
    result: dict[str, Any] = {
        "request_mode": "runpod_archive",
        "request_input": {"action": "refresh_trends", "chromadb_tar_base64": "<base64 omitted>"},
        "archive": {
            "collections": included_collections,
            "size_bytes": len(archive_bytes),
        },
    }
    if local_pipeline_result is not None:
        result["local_pipeline"] = local_pipeline_result
    if dry_run:
        result["dry_run"] = True
        return result

    request_input = {
        "action": "refresh_trends",
        "chromadb_tar_base64": base64.b64encode(archive_bytes).decode("ascii"),
    }
    runpod_response = _submit_runpod_job(
        request_input=request_input,
        endpoint_id=endpoint_id,
        api_key=api_key,
        base_url=base_url,
        sync=sync,
        wait=wait,
        timeout=timeout,
        poll_interval=poll_interval,
    )
    result["runpod_response"] = runpod_response
    return result


def run_local_refresh_trends_pipeline(
    *,
    steps: str | Iterable[str] | None = None,
) -> dict[str, Any]:
    normalized_steps = parse_refresh_steps(steps) or list(DEFAULT_REFRESH_STEPS)
    result = refresh_trends(steps=normalized_steps)
    if not result.get("success", False):
        raise TrendRefreshError(f"Local trend refresh failed: {json.dumps(result, ensure_ascii=False)}")
    return result


def build_chromadb_archive(
    *,
    include_ncs: bool = True,
    include_styles: bool = True,
    stores_root: str | Path | None = None,
) -> tuple[bytes, list[str]]:
    store_dir = Path(stores_root).resolve() if stores_root else RAG_STORE_DIR
    if not store_dir.is_dir():
        raise TrendRefreshError(f"ChromaDB store directory does not exist: {store_dir}")

    collection_names = ["chromadb_trends"]
    if include_ncs:
        collection_names.append("chromadb_ncs")
    if include_styles:
        collection_names.append("chromadb_styles")

    included: list[str] = []
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for collection_name in collection_names:
            source_dir = store_dir / collection_name
            if not source_dir.is_dir():
                if collection_name == "chromadb_trends":
                    raise TrendRefreshError(f"Required ChromaDB directory is missing: {source_dir}")
                continue
            archive.add(source_dir, arcname=collection_name)
            included.append(collection_name)

    if not included:
        raise TrendRefreshError(f"No ChromaDB collections were archived from: {store_dir}")
    return buffer.getvalue(), included


def _submit_runpod_job(
    *,
    request_input: dict[str, Any],
    endpoint_id: str | None,
    api_key: str | None,
    base_url: str | None,
    sync: bool,
    wait: bool,
    timeout: int,
    poll_interval: float,
) -> dict[str, Any]:
    resolved_endpoint_id = endpoint_id or getattr(settings, "RUNPOD_TRENDS_ENDPOINT_ID", "")
    resolved_api_key = api_key or getattr(settings, "RUNPOD_API_KEY", "")
    resolved_base_url = (base_url or getattr(settings, "RUNPOD_BASE_URL", "https://api.runpod.ai/v2")).rstrip("/")

    if not resolved_endpoint_id:
        raise TrendRefreshError("RUNPOD_TRENDS_ENDPOINT_ID is not configured.")
    if not resolved_api_key:
        raise TrendRefreshError("RUNPOD_API_KEY is not configured.")

    route = "runsync" if sync else "run"
    url = f"{resolved_base_url}/{resolved_endpoint_id}/{route}"
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {resolved_api_key}",
            "Content-Type": "application/json",
        },
        json={"input": request_input},
        timeout=(timeout if sync else min(timeout, 60)),
    )
    response.raise_for_status()
    data = response.json()

    if sync:
        if isinstance(data, dict):
            status = str(data.get("status", "")).upper()
            if status in {"IN_QUEUE", "IN_PROGRESS"}:
                job_id = str(data.get("id", "")).strip()
                if not job_id:
                    raise TrendRefreshError(f"RunPod sync response did not contain a job id: {data}")
                return _poll_runpod_job(
                    endpoint_id=resolved_endpoint_id,
                    api_key=resolved_api_key,
                    base_url=resolved_base_url,
                    job_id=job_id,
                    timeout=timeout,
                    poll_interval=poll_interval,
                )
        return _extract_runpod_output(data)
    if not wait:
        return data if isinstance(data, dict) else {"output": data}

    job_id = str(data.get("id", "")).strip()
    if not job_id:
        raise TrendRefreshError(f"RunPod async response did not contain a job id: {data}")
    return _poll_runpod_job(
        endpoint_id=resolved_endpoint_id,
        api_key=resolved_api_key,
        base_url=resolved_base_url,
        job_id=job_id,
        timeout=timeout,
        poll_interval=poll_interval,
    )


def _poll_runpod_job(
    *,
    endpoint_id: str,
    api_key: str,
    base_url: str,
    job_id: str,
    timeout: int,
    poll_interval: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    status_url = f"{base_url}/{endpoint_id}/status/{job_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    while time.monotonic() < deadline:
        response = requests.get(status_url, headers=headers, timeout=min(timeout, 60))
        response.raise_for_status()
        data = response.json()
        status = str(data.get("status", "")).upper()

        if status == "COMPLETED":
            output_url = data.get("output_url")
            if output_url:
                output_response = requests.get(str(output_url), timeout=min(timeout, 120))
                output_response.raise_for_status()
                fetched = output_response.json()
                return fetched if isinstance(fetched, dict) else {"output": fetched}
            return _extract_runpod_output(data)

        if status in FAILED_RUNPOD_STATUSES:
            error = data.get("error")
            output = data.get("output")
            raise TrendRefreshError(
                f"RunPod job {job_id} finished with status {status}. "
                f"error={error!r} output={output!r}"
            )

        time.sleep(poll_interval)

    raise TrendRefreshError(f"RunPod job {job_id} did not complete within {timeout} seconds.")


def _extract_runpod_output(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"output": data}

    output = data.get("output")
    if isinstance(output, dict):
        return output
    if output is not None:
        return {"output": output}
    return data
