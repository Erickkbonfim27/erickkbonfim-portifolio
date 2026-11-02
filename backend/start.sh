#!/bin/sh
# Container entrypoint. One image, two Easypanel services from the same build:
# the API (default) and the worker (PORTFOLIO_ROLE=worker). The role is read at
# runtime because the build does not see the service's environment.
set -eu

if [ "${PORTFOLIO_ROLE:-api}" = "worker" ]; then
  exec /app/.venv/bin/portfolio worker
fi

# Behind Easypanel's proxy: trust X-Forwarded-* so request.client is the real IP
# (the rate limiter depends on it).
exec /app/.venv/bin/uvicorn portfolio.main:create_app --factory \
  --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips '*'
