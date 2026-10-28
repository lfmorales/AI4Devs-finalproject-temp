#!/usr/bin/env bash
# Gets a Cognito ID token for the development user and writes it to e2e/.auth/token.json.
# The email and the app client id are read from the repository's .env without being printed;
# the password is asked for without echo. Neither the password nor the token is ever printed.
set -euo pipefail

REGION="eu-central-1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E2E_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$(dirname "$E2E_DIR")/.env"
TOKEN_FILE="$E2E_DIR/.auth/token.json"

for tool in aws jq; do
  command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 1; }
done
[ -f "$ENV_FILE" ] || { echo "No .env found at the repository root." >&2; exit 1; }

# Read single values by name; the file is never sourced, so nothing in it is executed.
read_env() { grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }
email="$(read_env SEED_USER_EMAIL)"
client_id="$(read_env COGNITO_CLIENT_ID)"
[ -n "$email" ] && [ -n "$client_id" ] || { echo "SEED_USER_EMAIL or COGNITO_CLIENT_ID is empty in .env." >&2; exit 1; }

read -rs -p "Cognito password for the development user: " password
echo

# The request goes through stdin so the password never appears in the process list.
response="$(jq -n --arg client "$client_id" --arg user "$email" --arg pass "$password" \
  '{AuthFlow: "USER_PASSWORD_AUTH", ClientId: $client, AuthParameters: {USERNAME: $user, PASSWORD: $pass}}' \
  | aws cognito-idp initiate-auth --region "$REGION" --cli-input-json file:///dev/stdin --output json)" \
  || { echo "Cognito rejected the sign-in (wrong password, or USER_PASSWORD_AUTH is not enabled on the app client)." >&2; exit 1; }
unset password

id_token="$(jq -r '.AuthenticationResult.IdToken // empty' <<<"$response")"
[ -n "$id_token" ] || { echo "Cognito answered without an ID token (a challenge such as NEW_PASSWORD_REQUIRED?)." >&2; exit 1; }

mkdir -p "$(dirname "$TOKEN_FILE")"
umask 077
jq -n --arg token "$id_token" '{id_token: $token}' > "$TOKEN_FILE"
echo "Token written to e2e/.auth/token.json"
