#!/usr/bin/env bash
# Rebuilds the stack's data from nothing: drops the volumes, applies the migrations and loads the
# development and margin demonstration data. It destroys the database; run it deliberately.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

# Before anything is stopped: port 80 must be free or this project's own. A stack of another worktree that
# publishes it would make `up` fail with "port is already allocated", and the E2E would read the wrong stack.
command -v docker >/dev/null || { echo "docker is not available." >&2; exit 1; }
project="$(docker compose config --format json | python3 -c 'import json, sys; print(json.load(sys.stdin)["name"])')" \
  || { echo "Compose could not name this repository's project." >&2; exit 1; }
foreign=""
while IFS='|' read -r name label ports; do
  [ -n "$name" ] || continue
  # Only a host mapping of port 80 itself counts, not another host port mapped to a container's port 80.
  printf '%s' "$ports" | grep -Eq '(^|[[:space:],]):?[^[:space:],]*:80->' || continue
  [ "$label" = "$project" ] && continue
  if [ -n "$label" ]; then owner="project \"$label\""; else owner="not a Compose project"; fi
  foreign="${foreign:+$foreign, }$name ($owner)"
done < <(docker ps --filter publish=80 --format '{{.Names}}|{{.Label "com.docker.compose.project"}}|{{.Ports}}')
if [ -n "$foreign" ]; then
  echo "Port 80 is published by $foreign, not by this repository's Compose project \"$project\". Nothing was stopped. Stop that stack yourself, then run this script again." >&2
  exit 1
fi

# Runs a command with the local part of every email in its output (both streams) shown as ***. The exit code is
# the command's own, because the pipelines run under pipefail.
EMAIL_LOCAL_PART='[A-Za-z0-9._%+-]+@'
without_emails() {
  { "$@" 2>&1 1>&3 3>&- | sed -E "s/$EMAIL_LOCAL_PART/***@/g" >&2; } 3>&1 | sed -E "s/$EMAIL_LOCAL_PART/***@/g"
}

docker compose down -v
docker compose up -d
# The backend needs a moment before exec works; alembic is retried until the database accepts it.
for attempt in $(seq 1 30); do
  docker compose exec -T backend alembic upgrade head && break
  [ "$attempt" -lt 30 ] || { echo "The migrations did not run after 30 attempts." >&2; exit 1; }
  sleep 2
done
without_emails docker compose exec -T backend python -m scripts.seed_dev_data
without_emails docker compose exec -T backend python -m scripts.seed_margin_demo
docker compose restart nginx

for attempt in $(seq 1 30); do
  status="$(curl -s -o /dev/null -w '%{http_code}' http://localhost/api/health || true)"
  [ "$status" = "200" ] && { echo "Stack ready: /api/health answers 200."; exit 0; }
  sleep 2
done
echo "/api/health did not answer 200 after 60 seconds." >&2
exit 1
