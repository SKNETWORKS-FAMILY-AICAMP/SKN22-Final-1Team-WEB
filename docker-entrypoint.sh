#!/bin/sh
set -eu

# Provide stable non-secret runtime defaults even when EB environment
# properties are partially reset or omitted during a redeploy.
: "${BOOTSTRAP_RAG_ASSETS:=1}"
: "${TIME_ZONE:=Asia/Seoul}"
: "${TREND_SCHEDULER_TIMEZONE:=${TIME_ZONE}}"
: "${TREND_SCHEDULER_WEEKLY_DAY:=fri}"
: "${TREND_SCHEDULER_WEEKLY_HOUR:=8}"
: "${TREND_SCHEDULER_WEEKLY_MINUTE:=0}"
: "${TREND_SCHEDULER_STEPS:=crawl,refine,llm_refine,vectorize,rebuild_ncs}"
: "${TREND_REFINER_MODEL:=gemini-2.5-flash}"
: "${NCS_PDF_SYNC_SOURCE_DIR:=}"
: "${NCS_PDF_SYNC_OVERWRITE:=0}"
: "${NCS_PDF_SYNC_STRICT:=0}"
: "${NCS_PACKAGED_EXAMPLE_PDF_BOOTSTRAP:=1}"
: "${OPTIONAL_STARTUP_TASKS_BLOCKING:=0}"
: "${NCS_PDF_SYNC_BLOCKING:=${OPTIONAL_STARTUP_TASKS_BLOCKING}}"
: "${BOOTSTRAP_RAG_ASSETS_BLOCKING:=${OPTIONAL_STARTUP_TASKS_BLOCKING}}"

export BOOTSTRAP_RAG_ASSETS
export TIME_ZONE
export TREND_SCHEDULER_TIMEZONE
export TREND_SCHEDULER_WEEKLY_DAY
export TREND_SCHEDULER_WEEKLY_HOUR
export TREND_SCHEDULER_WEEKLY_MINUTE
export TREND_SCHEDULER_STEPS
export TREND_REFINER_MODEL
export NCS_PDF_SYNC_SOURCE_DIR
export NCS_PDF_SYNC_OVERWRITE
export NCS_PDF_SYNC_STRICT
export NCS_PACKAGED_EXAMPLE_PDF_BOOTSTRAP
export OPTIONAL_STARTUP_TASKS_BLOCKING
export NCS_PDF_SYNC_BLOCKING
export BOOTSTRAP_RAG_ASSETS_BLOCKING

BUNDLED_NCS_PDF_DIR="/app/data/rag/sources/ncs"

run_task() {
  task_name="$1"
  blocking="$2"
  shift 2

  if [ "${blocking}" = "1" ]; then
    echo "[entrypoint] running ${task_name} in blocking mode"
    "$@"
    return $?
  fi

  echo "[entrypoint] starting ${task_name} in background"
  (
    set +e
    "$@"
    status=$?
    if [ "${status}" -eq 0 ]; then
      echo "[entrypoint] ${task_name} finished"
    else
      echo "[entrypoint] warning: ${task_name} failed with exit=${status}"
    fi
  ) &
}

run_ncs_pdf_sync() {
  if [ -z "${NCS_PDF_SYNC_SOURCE_DIR}" ]; then
    return 0
  fi

  if [ "${NCS_PACKAGED_EXAMPLE_PDF_BOOTSTRAP}" = "1" ]; then
    mkdir -p "${NCS_PDF_SYNC_SOURCE_DIR}"
    if ! find "${NCS_PDF_SYNC_SOURCE_DIR}" -maxdepth 1 -type f -name '*.pdf' | grep -q .; then
      if find "${BUNDLED_NCS_PDF_DIR}" -maxdepth 1 -type f -name '*.pdf' | grep -q .; then
        echo "[entrypoint] bootstrapping packaged example NCS PDFs into ${NCS_PDF_SYNC_SOURCE_DIR}"
        cp -n "${BUNDLED_NCS_PDF_DIR}"/*.pdf "${NCS_PDF_SYNC_SOURCE_DIR}/"
      fi
    fi
  fi

  echo "[entrypoint] syncing NCS PDFs from ${NCS_PDF_SYNC_SOURCE_DIR}"
  if [ "${NCS_PDF_SYNC_OVERWRITE}" = "1" ] && [ "${NCS_PDF_SYNC_STRICT}" = "1" ]; then
    python manage.py sync_ncs_source_pdfs --source-dir "${NCS_PDF_SYNC_SOURCE_DIR}" --overwrite --strict
  elif [ "${NCS_PDF_SYNC_OVERWRITE}" = "1" ]; then
    python manage.py sync_ncs_source_pdfs --source-dir "${NCS_PDF_SYNC_SOURCE_DIR}" --overwrite
  elif [ "${NCS_PDF_SYNC_STRICT}" = "1" ]; then
    python manage.py sync_ncs_source_pdfs --source-dir "${NCS_PDF_SYNC_SOURCE_DIR}" --strict
  else
    python manage.py sync_ncs_source_pdfs --source-dir "${NCS_PDF_SYNC_SOURCE_DIR}"
  fi
}

run_rag_bootstrap() {
  if [ "${BOOTSTRAP_RAG_ASSETS}" != "1" ]; then
    return 0
  fi

  echo "[entrypoint] ensuring packaged RAG assets are available"
  if ! python manage.py bootstrap_rag_assets; then
    echo "[entrypoint] warning: packaged RAG asset bootstrap failed; continuing startup"
  fi
}

if [ -n "${NCS_PDF_SYNC_SOURCE_DIR}" ]; then
  run_task "sync_ncs_source_pdfs" "${NCS_PDF_SYNC_BLOCKING}" run_ncs_pdf_sync
fi

if [ "${BOOTSTRAP_RAG_ASSETS}" = "1" ]; then
  run_task "bootstrap_rag_assets" "${BOOTSTRAP_RAG_ASSETS_BLOCKING}" run_rag_bootstrap
fi

if [ "${ENABLE_TREND_SCHEDULER:-0}" = "1" ]; then
  echo "[entrypoint] starting trend scheduler"
  python manage.py run_trend_scheduler &
fi

exec "$@"
