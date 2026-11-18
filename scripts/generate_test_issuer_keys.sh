#!/usr/bin/env bash
# Generates the RSA key pair of the test issuer, for the end-to-end tests and API calls in development.
#
# The public key is mounted, read-only, into the development backend; the private key signs the test
# tokens and is never mounted into any service nor copied into any image. Both live under .secrets/,
# which git and every Docker build context ignore. It prints the two paths, never a key.
#
#   ./scripts/generate_test_issuer_keys.sh            # into .secrets/test-issuer, keeps an existing pair
#   ./scripts/generate_test_issuer_keys.sh --force    # replaces an existing pair
#   ./scripts/generate_test_issuer_keys.sh --out DIR  # into DIR instead (tests, verify_prod_images.sh)

set -euo pipefail

OUT="$(cd "$(dirname "$0")/.." && pwd)/.secrets/test-issuer"
FORCE=false

while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=true; shift ;;
    --out)
      [ $# -ge 2 ] || { echo "--out needs a directory" >&2; exit 2; }
      OUT="$2"; shift 2 ;;
    *) echo "Unknown option: $1 (expected --force or --out DIR)" >&2; exit 2 ;;
  esac
done

PUBLIC_DIR="$OUT/public"
PRIVATE_DIR="$OUT/private"
PUBLIC_KEY="$PUBLIC_DIR/public.pem"
PRIVATE_KEY="$PRIVATE_DIR/private.pem"

if { [ -e "$PUBLIC_KEY" ] || [ -e "$PRIVATE_KEY" ]; } && [ "$FORCE" != true ]; then
  echo "A test issuer key pair already exists in $OUT; it was left unchanged. Use --force to replace it." >&2
  exit 1
fi

mkdir -p "$PUBLIC_DIR" "$PRIVATE_DIR"
chmod 700 "$PRIVATE_DIR"

# Generated beside the final paths and moved at the end, so a failure leaves no half-written pair.
umask 077
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$PRIVATE_KEY.new" 2> /dev/null
openssl pkey -in "$PRIVATE_KEY.new" -pubout -out "$PUBLIC_KEY.new" 2> /dev/null
chmod 600 "$PRIVATE_KEY.new"
chmod 644 "$PUBLIC_KEY.new"
mv -f "$PRIVATE_KEY.new" "$PRIVATE_KEY"
mv -f "$PUBLIC_KEY.new" "$PUBLIC_KEY"

echo "Public key:  $PUBLIC_KEY"
echo "Private key: $PRIVATE_KEY"
