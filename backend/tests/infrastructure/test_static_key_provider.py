"""A signing key provider that loads one RSA public key from a local PEM file, once, with no network."""

import os
from collections.abc import Callable
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from app.domain.exceptions import InvalidIdentityTokenError
from app.infrastructure.auth.issuer_token_verifier import IssuerTokenVerifier
from app.infrastructure.auth.static_key_provider import (
    InvalidPublicKeyFileError,
    PemPublicKeyProvider,
)
from tests.fixtures.identity_tokens import ENTRA, OTHER_TEST_KEY, TEST_KEY, entra_token


def _write_public_pem(path: Path, key: RSAPrivateKey) -> Path:
    path.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return path


def _verifier(key_file: Path) -> IssuerTokenVerifier:
    return IssuerTokenVerifier(ENTRA, PemPublicKeyProvider(key_file))


def test_a_token_signed_with_the_matching_private_key_is_accepted(tmp_path: Path) -> None:
    verifier = _verifier(_write_public_pem(tmp_path / "public.pem", TEST_KEY))

    identity = verifier.verify(entra_token(key=TEST_KEY))

    assert (identity.issuer, identity.subject) == (ENTRA.issuer, "sujeto-de-prueba")


def test_a_token_signed_with_another_key_is_rejected(tmp_path: Path) -> None:
    verifier = _verifier(_write_public_pem(tmp_path / "public.pem", TEST_KEY))

    with pytest.raises(InvalidIdentityTokenError):
        verifier.verify(entra_token(key=OTHER_TEST_KEY))


def test_the_file_is_read_once_when_the_provider_is_built(tmp_path: Path) -> None:
    key_file = _write_public_pem(tmp_path / "public.pem", TEST_KEY)
    verifier = _verifier(key_file)
    key_file.unlink()

    assert verifier.verify(entra_token(key=TEST_KEY)).subject == "sujeto-de-prueba"


def _missing(tmp_path: Path) -> Path:
    return tmp_path / "missing.pem"


def _unreadable(tmp_path: Path) -> Path:
    if os.geteuid() == 0:
        pytest.skip("root reads files without read permission")
    path = _write_public_pem(tmp_path / "unreadable.pem", TEST_KEY)
    path.chmod(0o000)
    return path


def _not_pem(tmp_path: Path) -> Path:
    path = tmp_path / "not-pem.pem"
    path.write_text("this is not a key\n")
    return path


def _private_key_pem(tmp_path: Path) -> Path:
    path = tmp_path / "private.pem"
    path.write_bytes(
        TEST_KEY.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return path


def _not_rsa_pem(tmp_path: Path) -> Path:
    path = tmp_path / "ec-public.pem"
    path.write_bytes(
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return path


@pytest.mark.parametrize(
    "make_file",
    [_missing, _unreadable, _not_pem, _private_key_pem, _not_rsa_pem],
    ids=["missing", "unreadable", "not-pem", "private-key", "not-rsa"],
)
def test_an_unusable_key_file_raises_an_error_naming_the_path(
    tmp_path: Path, make_file: Callable[[Path], Path]
) -> None:
    key_file = make_file(tmp_path)

    with pytest.raises(InvalidPublicKeyFileError) as raised:
        PemPublicKeyProvider(key_file)

    assert str(key_file) in str(raised.value)
