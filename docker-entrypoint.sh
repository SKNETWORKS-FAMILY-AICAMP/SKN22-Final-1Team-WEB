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

export BOOTSTRAP_RAG_ASSETS
export TIME_ZONE
export TREND_SCHEDULER_TIMEZONE
export TREND_SCHEDULER_WEEKLY_DAY
export TREND_SCHEDULER_WEEKLY_HOUR
export TREND_SCHEDULER_WEEKLY_MINUTE
export TREND_SCHEDULER_STEPS
export TREND_REFINER_MODEL

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
