#!/usr/bin/env bash
# Rebuilds the stack's data from nothing: drops the volumes, applies the migrations and loads the
# development and margin demonstration data. It destroys the database; run it deliberately.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

docker compose down -v
docker compose up -d
# The backend needs a moment before exec works; alembic is retried until the database accepts it.
for attempt in $(seq 1 30); do
  docker compose exec -T backend alembic upgrade head && break
  [ "$attempt" -lt 30 ] || { echo "The migrations did not run after 30 attempts." >&2; exit 1; }
  sleep 2
done
docker compose exec -T backend python -m scripts.seed_dev_data
docker compose exec -T backend python -m scripts.seed_margin_demo
docker compose restart nginx

for attempt in $(seq 1 30); do
  status="$(curl -s -o /dev/null -w '%{http_code}' http://localhost/api/health || true)"
  [ "$status" = "200" ] && { echo "Stack ready: /api/health answers 200."; exit 0; }
  sleep 2
done
echo "/api/health did not answer 200 after 60 seconds." >&2
exit 1
