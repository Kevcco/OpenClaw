#!/bin/sh
set -eu

export PYTHONPATH=/app

wait_for_qdrant() {
  if [ -z "${QDRANT_URL:-}" ] || [ "${WAIT_FOR_QDRANT:-1}" = "0" ]; then
    return 0
  fi

  health_url="${QDRANT_URL%/}/healthz"
  attempts="${QDRANT_WAIT_SECONDS:-30}"
  i=0
  while [ "$i" -lt "$attempts" ]; do
    if python -c 'import sys, urllib.request
try:
    response = urllib.request.urlopen(sys.argv[1], timeout=2)
    raise SystemExit(0 if 200 <= response.status < 300 else 1)
except Exception:
    raise SystemExit(1)' "$health_url" >/dev/null 2>&1; then
      echo "qdrant is ready"
      return 0
    fi
    i=$((i + 1))
    sleep 1
  done
  echo "warning: qdrant did not become ready after ${attempts}s; keyword retrieval remains available" >&2
}

python scripts/init_db.py
wait_for_qdrant
exec gunicorn --bind 0.0.0.0:8080 --workers 1 run:app
