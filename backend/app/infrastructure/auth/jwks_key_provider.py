"""The signing keys of an issuer that publishes them at a key address (Entra), cached and reloaded sparingly.

PyJWKClient on its own downloads the key set again whenever a token names a kid it does not hold, so anyone without
a session could make the backend call the issuer on every request, each call able to hold a thread for its whole
timeout. This provider bounds both: at most one download a minute, whatever the kid, and five seconds per download.
"""

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import jwt
from jwt import (
    PyJWK,
    PyJWKClient,
    PyJWKClientConnectionError,
    PyJWKClientError,
    PyJWKSet,
)

# How long one download of the key set may take before the issuer counts as unavailable.
JWKS_DOWNLOAD_TIMEOUT_SECONDS = 5.0
# The least time between two downloads: a kid that is not in the cache waits for the next one. The same interval is
# how long a kid seen as unknown is remembered, since no download happens before it ends.
JWKS_RELOAD_INTERVAL_SECONDS = 60.0
# How long a downloaded key set is used before a known kid renews it.
JWKS_LIFETIME_SECONDS = 3600.0

KeySetDownloader = Callable[[str, float], Mapping[str, Any]]
Clock = Callable[[], float]


@dataclass(frozen=True)
class _CachedKeySet:
    """One downloaded key set and when it was loaded. Replaced whole on every download and never modified, so a
    reader without the lock sees either the old set or the new one, never a mixture."""

    keys: Mapping[str, PyJWK]
    loaded_at: float


def download_key_set(url: str, timeout: float) -> Mapping[str, Any]:
    """One download of the key set, through PyJWKClient's HTTP (no redirects) with its own cache off."""
    data: Mapping[str, Any] = PyJWKClient(url, cache_jwk_set=False, timeout=timeout).fetch_data()
    return data


class CachedJwksKeyProvider:
    """Implements SigningKeyProvider for an issuer's key address. Building it touches no network: the first download
    happens with the first token, so the backend starts whether or not the issuer answers."""

    def __init__(
        self,
        url: str,
        *,
        download: KeySetDownloader = download_key_set,
        clock: Clock = time.monotonic,
    ) -> None:
        self._url = url
        self._download = download
        self._clock = clock
        self._lock = threading.Lock()
        self._cached: _CachedKeySet | None = None
        self._last_attempt_at: float | None = None
        self._last_attempt_failed = False

    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        kid = jwt.get_unverified_header(token).get("kid")
        if not isinstance(kid, str) or not kid:
            raise PyJWKClientError("The token names no signing key")

        # A known kid of a current key set never waits: no lock, so a download in progress does not hold it up.
        key = self._current_key(self._cached, kid)
        if key is not None:
            return key

        # The lock is for deciding and downloading only. Inside, check again: a request that waited for it may find
        # that another one has just downloaded, so simultaneous requests still cause at most one download.
        with self._lock:
            cached = self._cached
            key = self._current_key(cached, kid)
            if key is not None:
                return key
            if self._may_download():
                cached = self._reload()
            key = cached.keys.get(kid) if cached is not None else None
            if key is not None:
                return key
            if self._last_attempt_failed and cached is None:
                # Nothing was ever loaded and the last download failed: still unavailable, without asking again.
                raise PyJWKClientConnectionError("The issuer's keys could not be downloaded")
            raise PyJWKClientError("The token's signing key is not one of the issuer's keys")

    def _current_key(self, cached: _CachedKeySet | None, kid: str) -> PyJWK | None:
        """The key of the kid, when the key set holds it and has not expired."""
        if cached is None or self._clock() - cached.loaded_at >= JWKS_LIFETIME_SECONDS:
            return None
        return cached.keys.get(kid)

    def _may_download(self) -> bool:
        return self._last_attempt_at is None or self._clock() - self._last_attempt_at >= JWKS_RELOAD_INTERVAL_SECONDS

    def _reload(self) -> _CachedKeySet:
        self._last_attempt_at = self._clock()
        try:
            key_set = PyJWKSet.from_dict(dict(self._download(self._url, JWKS_DOWNLOAD_TIMEOUT_SECONDS)))
        except Exception as error:
            # Unreachable, slow or answering something that is not a usable key set: the issuer is unavailable.
            # The keys already cached are kept.
            self._last_attempt_failed = True
            raise PyJWKClientConnectionError("The issuer's keys could not be downloaded") from error
        self._cached = _CachedKeySet(
            keys=MappingProxyType({key.key_id: key for key in key_set.keys if key.key_id}),
            loaded_at=self._last_attempt_at,
        )
        self._last_attempt_failed = False
        return self._cached
