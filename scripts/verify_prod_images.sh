#!/usr/bin/env bash
# Builds the production images and checks them locally, with throwaway settings.
#
# It uses its own Compose project (adops360-verify), a generated .env with dummy values (the real .env is never
# read), a temporary database in a throwaway volume and a self-signed certificate generated on the spot. It
# calls no external service and always removes everything it created. The last line is "OK" or "FALLO: <reason>".
#
#   ./scripts/verify_prod_images.sh

set -u
cd "$(dirname "$0")/.." || exit 1

PROJECT=adops360-verify
COMPOSE_FILE=docker-compose.prod.yml
HTTP_PORT=18080
HTTPS_PORT=18443
WORK=$(mktemp -d)
REASON=""

compose() {
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" --env-file "$WORK/env" "$@"
}

cleanup() {
  compose down -v --remove-orphans > /dev/null 2>&1
  rm -rf "$WORK"
}

# Records why and leaves at once; finish() (the EXIT trap) removes everything and prints the last line.
stop() {
  REASON="$1"
  exit 1
}

finish() {
  local code=$?
  trap - EXIT
  cleanup
  if [ "$code" -eq 0 ] && [ -z "$REASON" ]; then
    echo "OK: images built, /api/health 200 over HTTPS, port 80 redirects, backend image clean and non-root, database not published, migrations applied as a separate step"
    exit 0
  fi
  echo "FALLO: ${REASON:-unexpected error or interruption (exit $code)}"
  exit 1
}

write_dummy_settings() {
  cat > "$WORK/env" <<EOF
POSTGRES_USER=verify
POSTGRES_PASSWORD=$(openssl rand -hex 12)
POSTGRES_DB=verify
COGNITO_REGION=eu-west-1
COGNITO_USER_POOL_ID=eu-west-1_verify
COGNITO_CLIENT_ID=verify-client
COGNITO_DOMAIN=verify.auth.eu-west-1.amazoncognito.com
NEXT_PUBLIC_API_URL=https://localhost:${HTTPS_PORT}/api
SERVER_NAME=localhost
EOF
  chmod 600 "$WORK/env"
  export ENV_FILE="$WORK/env" HTTP_PORT HTTPS_PORT
}

make_self_signed_certificate() {
  mkdir -p "$WORK/tls"
  docker run --rm --user "$(id -u):$(id -g)" -v "$WORK/tls:/out" --entrypoint openssl nginx:1.27 \
    req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost" \
    -keyout /out/privkey.pem -out /out/fullchain.pem > /dev/null 2>&1 || return 1
  compose up --no-start > "$WORK/create.log" 2>&1 || return 1
  docker run --rm -v "${PROJECT}_certbot_certs:/le" -v "$WORK/tls:/src:ro" --entrypoint sh nginx:1.27 \
    -c "mkdir -p /le/live/localhost && cp /src/fullchain.pem /src/privkey.pem /le/live/localhost/" || return 1
}

check_build() {
  compose build > "$WORK/build.log" 2>&1 || { tail -20 "$WORK/build.log"; stop "the images do not build"; }
}

check_stack_starts() {
  compose up -d --wait --wait-timeout 240 > "$WORK/up.log" 2>&1 || { tail -20 "$WORK/up.log"; stop "the production composition does not become healthy"; }
}

check_health_over_https() {
  local code
  code=$(curl -s --cacert "$WORK/tls/fullchain.pem" --resolve "localhost:${HTTPS_PORT}:127.0.0.1" \
    -o /dev/null -w '%{http_code}' "https://localhost:${HTTPS_PORT}/api/health")
  [ "$code" = "200" ] || stop "/api/health answered $code over HTTPS, not 200"
}

check_http_redirects_and_leaves_acme_open() {
  local redirect acme
  redirect=$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "http://127.0.0.1:${HTTP_PORT}/some/path" -H 'Host: localhost')
  [ "$redirect" = "301 https://localhost/some/path" ] || stop "port 80 did not redirect to HTTPS (got: $redirect)"
  acme=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${HTTP_PORT}/.well-known/acme-challenge/probe" -H 'Host: localhost')
  [ "$acme" = "404" ] || stop "the ACME challenge path is not served directly (got: $acme)"
}

check_backend_image_contents() {
  local image="${PROJECT}-backend"
  docker run --rm --entrypoint sh "$image" -c '
    test ! -e tests && test ! -e scripts/seed_dev_data.py && test ! -e /opt/venv/bin/pytest &&
    ! python -c "import pytest" 2> /dev/null &&
    test -f scripts/run_ingestion.py && test -f scripts/grant_roles.py && test -d alembic/versions' \
    || stop "the backend image has pytest, tests/ or seed_dev_data.py, or lacks run_ingestion.py, grant_roles.py or the migrations"
}

check_backend_is_not_root() {
  local running image_user
  image_user=$(docker run --rm --entrypoint id "${PROJECT}-backend" -u)
  running=$(compose exec -T backend id -u)
  { [ "$image_user" != "0" ] && [ "$running" != "0" ]; } || stop "the backend runs as root"
}

check_database_is_not_published() {
  local service published
  for service in db backend frontend; do
    published=$(docker port "$(compose ps -q "$service")" 2> /dev/null)
    [ -z "$published" ] || stop "the $service service publishes a port"
  done
}

check_migrations_are_a_separate_step() {
  local before after current
  before=$(compose exec -T db psql -U verify -d verify -tAc "select to_regclass('public.alembic_version')")
  [ -z "$before" ] || stop "the migrations were applied at start"
  compose run --rm backend alembic upgrade head > "$WORK/migrate.log" 2>&1 || { tail -20 "$WORK/migrate.log"; stop "alembic upgrade head failed"; }
  after=$(compose exec -T db psql -U verify -d verify -tAc "select to_regclass('public.alembic_version')")
  [ -n "$after" ] || stop "alembic upgrade head left no version table"
  current=$(compose run --rm backend alembic current 2> /dev/null)
  case "$current" in *"(head)"*) ;; *) stop "the database is not at head after the explicit step";; esac
}

check_first_user_command() {
  local output
  output=$(compose run --rm backend python -m scripts.grant_roles first@example.org operations 2>&1)
  case "$output" in *"user created: 1"*) ;; *) stop "grant_roles did not create the first user";; esac
}

verify() {
  write_dummy_settings
  check_build
  make_self_signed_certificate || stop "could not prepare the temporary database and certificate"
  check_stack_starts
  check_health_over_https
  check_http_redirects_and_leaves_acme_open
  check_backend_image_contents
  check_backend_is_not_root
  check_database_is_not_published
  check_migrations_are_a_separate_step
  check_first_user_command
}

# An interruption is a failure, whatever status the interrupted command had.
trap 'REASON="${REASON:-interrupted}"; exit 1' INT TERM
trap finish EXIT
verify
