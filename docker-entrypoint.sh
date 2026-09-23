#!/bin/sh
set -eu

export PYTHONPATH=/app
python scripts/init_db.py
exec gunicorn --bind 0.0.0.0:8080 --workers 1 run:app
