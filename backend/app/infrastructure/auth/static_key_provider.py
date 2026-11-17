from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key


class InvalidPublicKeyFileError(ValueError):
    """The PEM file of a static key provider is missing, unreadable or not an RSA public key."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"Public key file {path}: {reason}")
        self.path = path


@dataclass(frozen=True)
class StaticSigningKey:
    key: RSAPublicKey


class PemPublicKeyProvider:
    """A SigningKeyProvider holding one RSA public key, read once from a local PEM file; no network.

    It returns the same key for every token, with or without a kid: the signature,
    which IssuerTokenVerifier still checks, is what makes a token valid.
    """

    def __init__(self, path: Path) -> None:
        try:
            pem = path.read_bytes()
        except OSError as error:
            raise InvalidPublicKeyFileError(path, f"cannot be read ({error.strerror})") from error
        try:
            public_key = load_pem_public_key(pem)
        except (ValueError, UnsupportedAlgorithm) as error:
            raise InvalidPublicKeyFileError(path, "does not hold a PEM public key") from error
        if not isinstance(public_key, RSAPublicKey):
            raise InvalidPublicKeyFileError(path, "does not hold an RSA public key")
        self._signing_key = StaticSigningKey(key=public_key)

    def get_signing_key_from_jwt(self, token: str) -> StaticSigningKey:
        return self._signing_key
