"""PEM key files for the tests of the static key provider and of the test issuer."""

import os
from collections.abc import Callable
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from tests.fixtures.identity_tokens import TEST_KEY


def write_public_pem(path: Path, key: RSAPrivateKey) -> Path:
    path.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return path


def _missing(tmp_path: Path) -> Path:
    return tmp_path / "missing.pem"


def _unreadable(tmp_path: Path) -> Path:
    if os.geteuid() == 0:
        pytest.skip("root reads files without read permission")
    path = write_public_pem(tmp_path / "unreadable.pem", TEST_KEY)
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


# Each builder writes, under tmp_path, a key file the provider must refuse.
UNUSABLE_KEY_FILES: list[Callable[[Path], Path]] = [_missing, _unreadable, _not_pem, _private_key_pem, _not_rsa_pem]
UNUSABLE_KEY_FILE_IDS = ["missing", "unreadable", "not-pem", "private-key", "not-rsa"]
