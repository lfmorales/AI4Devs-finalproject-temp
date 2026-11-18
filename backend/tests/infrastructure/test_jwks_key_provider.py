"""The key provider of the Entra issuer: a cached key set, reloaded at most once a minute for an unknown kid, with a
bounded download time. No network: a fake downloader counts the downloads and a fake clock moves the time."""

import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from jwt import PyJWKClientConnectionError
from jwt.algorithms import RSAAlgorithm

from app.config import TEST_ISSUER, TEST_ISSUER_AUDIENCE, TokenIssuer
from app.domain.exceptions import (
    IdentityProviderUnavailableError,
    InvalidIdentityTokenError,
)
from app.infrastructure.auth.issuer_token_verifier import IssuerTokenVerifier
from app.infrastructure.auth.jwks_key_provider import (
    JWKS_DOWNLOAD_TIMEOUT_SECONDS,
    CachedJwksKeyProvider,
)
from app.infrastructure.auth.static_key_provider import PemPublicKeyProvider
from app.presentation.dependencies import providers
from tests.fixtures.identity_tokens import ENTRA, OTHER_TEST_KEY, TEST_KEY
from tests.fixtures.key_files import write_public_pem

KEYS_URL = ENTRA.jwks_url or ""


def _jwk(key: RSAPrivateKey, kid: str) -> dict[str, Any]:
    jwk: dict[str, Any] = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    return {**jwk, "kid": kid, "use": "sig", "alg": "RS256"}


def _key_set(*keys: tuple[RSAPrivateKey, str]) -> dict[str, Any]:
    return {"keys": [_jwk(key, kid) for key, kid in keys]}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class CountingDownloader:
    """Answers with the current key set, or raises the current error, and records every call."""

    def __init__(self, key_set: Mapping[str, Any], delay_seconds: float = 0.0) -> None:
        self.key_set = key_set
        self.error: Exception | None = None
        self.calls: list[tuple[str, float]] = []
        self._delay_seconds = delay_seconds
        self._lock = threading.Lock()

    def __call__(self, url: str, timeout: float) -> Mapping[str, Any]:
        with self._lock:
            self.calls.append((url, timeout))
        if self._delay_seconds:
            time.sleep(self._delay_seconds)
        if self.error is not None:
            raise self.error
        return self.key_set


def _token(kid: str | None, key: RSAPrivateKey = TEST_KEY) -> str:
    now = int(time.time())
    claims = {
        "iss": ENTRA.issuer,
        "aud": ENTRA.audience,
        "iat": now,
        "exp": now + 3600,
        "oid": "sujeto-de-prueba",
        "ver": "2.0",
        "scp": "access_as_user",
    }
    headers = {"kid": kid} if kid is not None else None
    return jwt.encode(claims, key, algorithm="RS256", headers=headers)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def downloader() -> CountingDownloader:
    return CountingDownloader(_key_set((TEST_KEY, "clave-a")))


@pytest.fixture
def verifier(clock: FakeClock, downloader: CountingDownloader) -> IssuerTokenVerifier:
    return IssuerTokenVerifier(ENTRA, CachedJwksKeyProvider(KEYS_URL, download=downloader, clock=clock))


def test_building_the_provider_downloads_nothing(clock: FakeClock, downloader: CountingDownloader) -> None:
    CachedJwksKeyProvider(KEYS_URL, download=downloader, clock=clock)

    assert downloader.calls == []


def test_a_known_kid_does_not_download_after_the_first_load(
    verifier: IssuerTokenVerifier, clock: FakeClock, downloader: CountingDownloader
) -> None:
    for seconds in (0, 10, 100, 1000, 3000):
        clock.now = 1000.0 + seconds
        assert verifier.verify(_token("clave-a")).subject == "sujeto-de-prueba"

    assert len(downloader.calls) == 1


def test_an_unknown_kid_downloads_once_then_is_rejected_without_network_until_a_minute_has_passed(
    verifier: IssuerTokenVerifier, clock: FakeClock, downloader: CountingDownloader
) -> None:
    verifier.verify(_token("clave-a"))  # first load
    clock.now += 100

    with pytest.raises(InvalidIdentityTokenError):
        verifier.verify(_token("clave-desconocida"))
    assert len(downloader.calls) == 2

    clock.now += 10
    with pytest.raises(InvalidIdentityTokenError):
        verifier.verify(_token("clave-desconocida"))
    assert len(downloader.calls) == 2

    clock.now += 51  # 61 seconds after the reload
    with pytest.raises(InvalidIdentityTokenError):
        verifier.verify(_token("clave-desconocida"))
    assert len(downloader.calls) == 3


def test_a_hundred_different_unknown_kids_in_a_minute_cause_a_single_download(
    verifier: IssuerTokenVerifier, clock: FakeClock, downloader: CountingDownloader
) -> None:
    for n in range(100):
        clock.now = 1000.0 + n * 0.5
        with pytest.raises(InvalidIdentityTokenError):
            verifier.verify(_token(f"clave-desconocida-{n}"))

    assert len(downloader.calls) == 1


def test_a_token_without_kid_is_rejected_without_network(
    verifier: IssuerTokenVerifier, downloader: CountingDownloader
) -> None:
    with pytest.raises(InvalidIdentityTokenError):
        verifier.verify(_token(None))

    assert downloader.calls == []


def test_a_legitimate_rotation_is_accepted_once_the_new_kid_appears_after_the_download(
    verifier: IssuerTokenVerifier, clock: FakeClock, downloader: CountingDownloader
) -> None:
    verifier.verify(_token("clave-a"))
    downloader.key_set = _key_set((TEST_KEY, "clave-a"), (OTHER_TEST_KEY, "clave-b"))
    clock.now += 61

    assert verifier.verify(_token("clave-b", OTHER_TEST_KEY)).subject == "sujeto-de-prueba"
    assert len(downloader.calls) == 2


def test_a_network_failure_is_unavailable_and_keeps_the_cached_keys(
    verifier: IssuerTokenVerifier, clock: FakeClock, downloader: CountingDownloader
) -> None:
    verifier.verify(_token("clave-a"))
    downloader.error = PyJWKClientConnectionError("connection refused")
    clock.now += 61

    with pytest.raises(IdentityProviderUnavailableError):
        verifier.verify(_token("clave-desconocida"))

    clock.now += 1
    assert verifier.verify(_token("clave-a")).subject == "sujeto-de-prueba"
    assert len(downloader.calls) == 2


def test_after_a_failed_first_load_tokens_stay_unavailable_without_network_for_a_minute(
    verifier: IssuerTokenVerifier, clock: FakeClock, downloader: CountingDownloader
) -> None:
    downloader.error = PyJWKClientConnectionError("connection refused")

    with pytest.raises(IdentityProviderUnavailableError):
        verifier.verify(_token("clave-a"))
    clock.now += 30
    with pytest.raises(IdentityProviderUnavailableError):
        verifier.verify(_token("clave-a"))
    assert len(downloader.calls) == 1

    downloader.error = None
    clock.now += 31
    assert verifier.verify(_token("clave-a")).subject == "sujeto-de-prueba"
    assert len(downloader.calls) == 2


def test_two_simultaneous_requests_with_the_same_unknown_kid_cause_a_single_download(clock: FakeClock) -> None:
    slow_downloader = CountingDownloader(_key_set((TEST_KEY, "clave-a")), delay_seconds=0.2)
    verifier = IssuerTokenVerifier(ENTRA, CachedJwksKeyProvider(KEYS_URL, download=slow_downloader, clock=clock))
    start = threading.Barrier(2)
    outcomes: list[type[Exception]] = []

    def request() -> None:
        start.wait()
        try:
            verifier.verify(_token("clave-desconocida"))
        except Exception as error:  # noqa: BLE001 - the outcome is what the test checks
            outcomes.append(type(error))

    threads = [threading.Thread(target=request) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert len(slow_downloader.calls) == 1
    assert outcomes == [InvalidIdentityTokenError, InvalidIdentityTokenError]


def test_after_an_hour_a_known_kid_renews_the_key_set(
    verifier: IssuerTokenVerifier, clock: FakeClock, downloader: CountingDownloader
) -> None:
    verifier.verify(_token("clave-a"))
    clock.now += 3599
    verifier.verify(_token("clave-a"))
    assert len(downloader.calls) == 1

    clock.now += 1
    assert verifier.verify(_token("clave-a")).subject == "sujeto-de-prueba"
    assert len(downloader.calls) == 2


def test_the_configured_timeout_reaches_the_downloader(
    verifier: IssuerTokenVerifier, downloader: CountingDownloader
) -> None:
    verifier.verify(_token("clave-a"))

    assert JWKS_DOWNLOAD_TIMEOUT_SECONDS == 5
    assert downloader.calls == [(KEYS_URL, JWKS_DOWNLOAD_TIMEOUT_SECONDS)]


def test_the_wiring_uses_the_cached_provider_for_entra_and_the_pem_provider_for_the_test_issuer(
    tmp_path: Path,
) -> None:
    test_issuer = TokenIssuer(
        kind="entra",
        issuer=TEST_ISSUER,
        audience=TEST_ISSUER_AUDIENCE,
        jwks_url=None,
        user_claim="oid",
        required_scope="access_as_user",
        public_key_file=write_public_pem(tmp_path / "public.pem", TEST_KEY),
    )

    assert isinstance(providers._issuer_verifier(ENTRA).key_provider, CachedJwksKeyProvider)
    assert isinstance(providers._issuer_verifier(test_issuer).key_provider, PemPublicKeyProvider)


class BlockingDownloader:
    """Answers with its key set, but each call waits until the test releases it; `entered` tells the test a call
    is in progress."""

    def __init__(self, key_set: Mapping[str, Any]) -> None:
        self.key_set = key_set
        self.calls = 0
        self.entered = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()

    def __call__(self, url: str, timeout: float) -> Mapping[str, Any]:
        with self._lock:
            self.calls += 1
        self.entered.set()
        assert self.release.wait(timeout=10)
        return self.key_set


def test_a_known_current_kid_is_served_while_a_download_is_in_progress(clock: FakeClock) -> None:
    downloader = BlockingDownloader(_key_set((TEST_KEY, "clave-a")))
    verifier = IssuerTokenVerifier(ENTRA, CachedJwksKeyProvider(KEYS_URL, download=downloader, clock=clock))
    downloader.release.set()
    verifier.verify(_token("clave-a"))  # first load
    downloader.release.clear()
    downloader.entered.clear()
    clock.now += 61
    known_outcome: list[str] = []

    def unknown_kid_request() -> None:
        with pytest.raises(InvalidIdentityTokenError):
            verifier.verify(_token("clave-desconocida"))

    def known_kid_request() -> None:
        known_outcome.append(verifier.verify(_token("clave-a")).subject)

    downloading = [threading.Thread(target=unknown_kid_request) for _ in range(2)]
    try:
        downloading[0].start()
        assert downloader.entered.wait(timeout=5)
        downloading[1].start()
        known = threading.Thread(target=known_kid_request)
        known.start()
        known.join(timeout=1)

        assert not known.is_alive(), "a known kid waited for the download"
        assert known_outcome == ["sujeto-de-prueba"]
    finally:
        downloader.release.set()
        for thread in downloading:
            thread.join(timeout=5)

    assert downloader.calls == 2  # the first load and one download for the two simultaneous unknown kids
