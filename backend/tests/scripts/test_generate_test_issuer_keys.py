"""scripts/generate_test_issuer_keys.sh: the test issuer's key pair, with tight modes, never overwritten by accident.

The script lives at the repository root, outside the backend. The tests are skipped only where the
repository is absent (inside a backend container), and always write into tmp_path through --out,
never into .secrets/.
"""

import stat
import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from app.infrastructure.auth.issuer_token_verifier import IssuerTokenVerifier
from app.infrastructure.auth.static_key_provider import PemPublicKeyProvider
from tests.fixtures.identity_tokens import ENTRA, entra_token

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "generate_test_issuer_keys.sh"

# Skipped only where the repository is absent (a backend container); a missing script is a failure.
pytestmark = pytest.mark.skipif(
    not (REPOSITORY_ROOT / "docker-compose.yml").is_file(), reason="the repository root is not present"
)


def _run(out: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), "--out", str(out), *arguments], capture_output=True, text=True, timeout=60, check=False
    )


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _private_key(path: Path) -> RSAPrivateKey:
    key = load_pem_private_key(path.read_bytes(), password=None)
    assert isinstance(key, RSAPrivateKey)
    return key


def test_it_creates_the_pair_in_two_directories_with_tight_modes(tmp_path: Path) -> None:
    out = tmp_path / "test-issuer"

    result = _run(out)

    assert result.returncode == 0, result.stderr
    public, private = out / "public" / "public.pem", out / "private" / "private.pem"
    assert public.read_text().startswith("-----BEGIN PUBLIC KEY-----")
    assert (_mode(out / "private"), _mode(private)) == (0o700, 0o600)
    assert _private_key(private).key_size == 2048


def test_it_prints_both_paths_and_never_a_key(tmp_path: Path) -> None:
    out = tmp_path / "test-issuer"

    result = _run(out)

    assert str(out / "public" / "public.pem") in result.stdout
    assert str(out / "private" / "private.pem") in result.stdout
    assert "BEGIN" not in result.stdout + result.stderr


def test_the_private_key_signs_a_token_the_public_key_provider_accepts(tmp_path: Path) -> None:
    out = tmp_path / "test-issuer"
    _run(out)
    verifier = IssuerTokenVerifier(ENTRA, PemPublicKeyProvider(out / "public" / "public.pem"))

    identity = verifier.verify(entra_token(key=_private_key(out / "private" / "private.pem")))

    assert identity.subject == "sujeto-de-prueba"


def test_without_force_an_existing_pair_is_kept_and_the_script_says_so(tmp_path: Path) -> None:
    out = tmp_path / "test-issuer"
    _run(out)
    before = ((out / "public" / "public.pem").read_bytes(), (out / "private" / "private.pem").read_bytes())

    result = _run(out)

    assert result.returncode != 0
    assert "--force" in result.stderr
    assert ((out / "public" / "public.pem").read_bytes(), (out / "private" / "private.pem").read_bytes()) == before


def test_with_force_the_pair_is_replaced_with_the_same_modes(tmp_path: Path) -> None:
    out = tmp_path / "test-issuer"
    _run(out)
    before = (out / "private" / "private.pem").read_bytes()

    result = _run(out, "--force")

    assert result.returncode == 0, result.stderr
    assert (out / "private" / "private.pem").read_bytes() != before
    assert (_mode(out / "private"), _mode(out / "private" / "private.pem")) == (0o700, 0o600)
