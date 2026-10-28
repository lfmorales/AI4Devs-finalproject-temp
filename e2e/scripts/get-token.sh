#!/usr/bin/env bash
# Gets a Cognito ID token for the development user and writes it to e2e/.auth/token.json.
#
# The email and the app client id are read from the repository's .env by name (the file is never sourced)
# and cleaned of quotes, spaces and carriage returns. Python then asks Cognito for the token over HTTPS with
# the standard library only; it reads the password itself from the terminal, so the password never goes
# through this shell, an environment variable, a command-line argument or a file. Nothing sensitive is
# printed: neither the password, the token, the request nor Cognito's answer.
#
# For the tests only: E2E_ENV_FILE and E2E_TOKEN_FILE move the two files, E2E_PASSWORD replaces the prompt
# and E2E_COGNITO_ENDPOINT points at a fake Cognito, which is accepted for localhost and 127.0.0.1 only.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E2E_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${E2E_ENV_FILE:-$(dirname "$E2E_DIR")/.env}"
TOKEN_FILE="${E2E_TOKEN_FILE:-$E2E_DIR/.auth/token.json}"

command -v python3 >/dev/null || { echo "Missing tool: python3" >&2; exit 2; }
[ -f "$ENV_FILE" ] || { echo "No .env found at the repository root." >&2; exit 2; }

# One value by name: the last assignment, without carriage returns, then trimmed, unquoted and trimmed again.
read_env() {
  grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- | tr -d '\r' \
    | sed -E -e 's/^[[:space:]]+//' -e 's/[[:space:]]+$//' \
             -e "s/^\"(.*)\"\$/\\1/" -e "s/^'(.*)'\$/\\1/" \
    | sed -E -e 's/^[[:space:]]+//' -e 's/[[:space:]]+$//' || true
}
email="$(read_env SEED_USER_EMAIL)"
client_id="$(read_env COGNITO_CLIENT_ID)"
missing=""
[ -n "$email" ] || missing="SEED_USER_EMAIL"
[ -n "$client_id" ] || missing="${missing:+$missing and }COGNITO_CLIENT_ID"
[ -z "$missing" ] || { echo ".env has no value for $missing." >&2; exit 2; }

E2E_COGNITO_USERNAME="$email" E2E_COGNITO_CLIENT_ID="$client_id" E2E_TOKEN_FILE="$TOKEN_FILE" \
python3 -I - <<'PYTHON'
import getpass
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

REGION = "eu-central-1"
LOCAL_HOSTS = {"localhost", "127.0.0.1"}

# Exit code and fixed message of every way this can end. None of them includes anything received or sent.
SCRIPT_FAULT = (2, "The script sent a request Cognito considers invalid (a script or configuration fault, not the credentials). Check COGNITO_CLIENT_ID in .env.")
CREDENTIALS = (3, "Cognito rejected the credentials: wrong password or unknown user. Check the password and SEED_USER_EMAIL in .env.")
FLOW_DISABLED = (4, "The app client does not allow USER_PASSWORD_AUTH. Enable it in the authentication flows of the Cognito app client.")
NEW_PASSWORD = (5, "Cognito requires a new password (NEW_PASSWORD_REQUIRED). Set a permanent password for the user, then run this script again.")
OTHER_CHALLENGE = (5, "Cognito asked for an extra step (a sign-in challenge) that this script cannot answer.")
CERTIFICATE = (6, "The TLS certificate of Cognito could not be verified. Install the certificates of this Python (on macOS, run \"Install Certificates.command\" from its installation folder). Verification is never disabled.")
UNREACHABLE = (7, "Cognito could not be reached. Check the network connection.")
ENDPOINT_REFUSED = (8, "E2E_COGNITO_ENDPOINT is only accepted for localhost or 127.0.0.1.")
UNEXPECTED = (9, "Cognito answered in a way this script does not recognise.")
NO_TOKEN = (9, "Cognito answered without an ID token.")
NO_PASSWORD = (2, "No password was given. Run this script from a terminal and type it when asked.")


def finish(outcome):
    code, message = outcome
    print(message, file=sys.stderr)
    sys.exit(code)


def endpoint() -> str:
    override = os.environ.get("E2E_COGNITO_ENDPOINT")
    if override is None:
        return f"https://cognito-idp.{REGION}.amazonaws.com/"
    if urllib.parse.urlparse(override).hostname not in LOCAL_HOSTS:
        finish(ENDPOINT_REFUSED)
    return override


def read_password() -> str:
    password = os.environ.get("E2E_PASSWORD")  # tests only; the password is otherwise typed
    if password is None:
        try:
            with open("/dev/tty"):
                pass
        except OSError:
            finish(NO_PASSWORD)
        password = getpass.getpass("Cognito password for the development user: ")
    if password == "":
        finish(NO_PASSWORD)
    return password


def classify_error(status: int, answer: object):
    error_type = ""
    message = ""
    if isinstance(answer, dict):
        error_type = str(answer.get("__type", "")).split("#")[-1]
        message = str(answer.get("message", answer.get("Message", "")))
    if error_type in ("NotAuthorizedException", "UserNotFoundException"):
        return CREDENTIALS
    if error_type == "InvalidParameterException" and re.search(r"flow not enabled", message, re.IGNORECASE):
        return FLOW_DISABLED
    if error_type in ("InvalidParameterException", "ResourceNotFoundException", "InvalidParameterType", "ValidationException", "SerializationException"):
        return SCRIPT_FAULT
    return UNEXPECTED


def main() -> None:
    url = endpoint()
    password = read_password()
    body = json.dumps({
        "AuthFlow": "USER_PASSWORD_AUTH",
        "ClientId": os.environ["E2E_COGNITO_CLIENT_ID"],
        "AuthParameters": {"USERNAME": os.environ["E2E_COGNITO_USERNAME"], "PASSWORD": password},
    }).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
        "Content-Type": "application/x-amz-json-1.1",
    })
    del body, password

    try:
        with urllib.request.urlopen(request, timeout=30, context=ssl.create_default_context()) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    except urllib.error.URLError as error:
        finish(CERTIFICATE if isinstance(error.reason, ssl.SSLCertVerificationError) else UNREACHABLE)
    except ssl.SSLCertVerificationError:
        finish(CERTIFICATE)
    except OSError:
        finish(UNREACHABLE)

    try:
        answer = json.loads(raw)
    except ValueError:
        answer = None

    if status != 200:
        finish(classify_error(status, answer))
    if not isinstance(answer, dict):
        finish(UNEXPECTED)
    if "ChallengeName" in answer:
        finish(NEW_PASSWORD if answer["ChallengeName"] == "NEW_PASSWORD_REQUIRED" else OTHER_CHALLENGE)
    result = answer.get("AuthenticationResult")
    id_token = result.get("IdToken") if isinstance(result, dict) else None
    if not isinstance(id_token, str) or id_token == "":
        finish(NO_TOKEN)

    token_file = os.environ["E2E_TOKEN_FILE"]
    os.makedirs(os.path.dirname(token_file), exist_ok=True)
    descriptor = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump({"id_token": id_token}, handle)
    os.chmod(token_file, 0o600)
    print("Token written to e2e/.auth/token.json")


main()
PYTHON
