"""A signing key provider that loads one RSA public key from a local PEM file, once, with no network."""

from collections.abc import Callable
from pathlib import Path

import pytest

from app.domain.exceptions import InvalidIdentityTokenError
from app.infrastructure.auth.issuer_token_verifier import IssuerTokenVerifier
from app.infrastructure.auth.static_key_provider import (
    InvalidPublicKeyFileError,
    PemPublicKeyProvider,
)
from tests.fixtures.identity_tokens import ENTRA, OTHER_TEST_KEY, TEST_KEY, entra_token
from tests.fixtures.key_files import (
    UNUSABLE_KEY_FILE_IDS,
    UNUSABLE_KEY_FILES,
    write_public_pem,
)


def _verifier(key_file: Path) -> IssuerTokenVerifier:
    return IssuerTokenVerifier(ENTRA, PemPublicKeyProvider(key_file))


def test_a_token_signed_with_the_matching_private_key_is_accepted(tmp_path: Path) -> None:
    verifier = _verifier(write_public_pem(tmp_path / "public.pem", TEST_KEY))

    identity = verifier.verify(entra_token(key=TEST_KEY))

    assert (identity.issuer, identity.subject) == (ENTRA.issuer, "sujeto-de-prueba")


def test_a_token_signed_with_another_key_is_rejected(tmp_path: Path) -> None:
    verifier = _verifier(write_public_pem(tmp_path / "public.pem", TEST_KEY))

    with pytest.raises(InvalidIdentityTokenError):
        verifier.verify(entra_token(key=OTHER_TEST_KEY))


def test_the_file_is_read_once_when_the_provider_is_built(tmp_path: Path) -> None:
    key_file = write_public_pem(tmp_path / "public.pem", TEST_KEY)
    verifier = _verifier(key_file)
    key_file.unlink()

    assert verifier.verify(entra_token(key=TEST_KEY)).subject == "sujeto-de-prueba"


@pytest.mark.parametrize(
    "make_file",
    UNUSABLE_KEY_FILES,
    ids=UNUSABLE_KEY_FILE_IDS,
)
def test_an_unusable_key_file_raises_an_error_naming_the_path(
    tmp_path: Path, make_file: Callable[[Path], Path]
) -> None:
    key_file = make_file(tmp_path)

    with pytest.raises(InvalidPublicKeyFileError) as raised:
        PemPublicKeyProvider(key_file)

    assert str(key_file) in str(raised.value)
