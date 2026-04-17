#!/bin/sh
set -e
exec python -m uvicorn app.main:create_app \
    --factory \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --no-access-log \
    --log-level critical
