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

if [ -n "${NCS_PDF_SYNC_SOURCE_DIR}" ]; then
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
fi

if [ "${BOOTSTRAP_RAG_ASSETS}" = "1" ]; then
  echo "[entrypoint] ensuring packaged RAG assets are available"
  if ! python manage.py bootstrap_rag_assets; then
    echo "[entrypoint] warning: packaged RAG asset bootstrap failed; continuing startup"
  fi
fi

if [ "${ENABLE_TREND_SCHEDULER:-0}" = "1" ]; then
  echo "[entrypoint] starting trend scheduler"
  python manage.py run_trend_scheduler &
fi

exec "$@"
