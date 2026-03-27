#!/bin/sh
set -eu

if [ "${ENABLE_TREND_SCHEDULER:-0}" = "1" ]; then
  echo "[entrypoint] starting trend scheduler"
  python manage.py run_trend_scheduler &
fi

exec "$@"
