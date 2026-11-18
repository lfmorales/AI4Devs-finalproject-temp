from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENTRA_AUTHORITY = "https://login.microsoftonline.com"
_ENTRA_USER_CLAIM = "oid"
_ENTRA_REQUIRED_SCOPE = "access_as_user"

# The test issuer signs in no person: it serves the end-to-end tests and API calls in development.
# Its iss and audience are fixed here and read from no variable, so its tokens never pass for a real issuer's.
TEST_ISSUER = "http://localhost/test-issuer/v2.0"
TEST_ISSUER_AUDIENCE = "api://adops360-test-issuer"
# APP_ENV values, compared exactly, under which the test issuer may be active.
_TEST_ISSUER_APP_ENVS = ("development", "test")


@dataclass(frozen=True)
class TokenIssuer:
    """An identity provider whose bearer tokens are accepted."""

    kind: Literal["entra"]
    issuer: str
    audience: str
    # Where the issuer publishes its keys, or None when they come from a local file.
    jwks_url: str | None
    # The claim that identifies the user at this issuer.
    user_claim: str
    # A scope the token must carry, or None when the issuer requires none.
    required_scope: str | None
    # A PEM file holding the issuer's one public key, used instead of jwks_url.
    public_key_file: Path | None = None


class Settings(BaseSettings):
    """Configuration read from environment variables. There are no defaults for secrets."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    database_url: str
    # Required: Entra is the one real issuer. Read as optional only so the validator below can name what is missing.
    entra_tenant_id: str | None = None
    entra_client_id: str | None = None
    # Optional so the application starts without a DSP; a connector that needs them reports it is not configured.
    adform_client_id: str | None = None
    adform_client_secret: SecretStr | None = None
    # The zone "today" and the D-7 to D-1 window are calendar days of; the UTC date is wrong around midnight in Madrid.
    app_timezone: str = "Europe/Madrid"
    # Where the backend runs; only "development" and "test" allow the test issuer.
    app_env: str | None = None
    # The PEM public key of the test issuer; without it the test issuer is not configured.
    test_issuer_public_key_file: Path | None = None

    @model_validator(mode="after")
    def _entra_is_configured(self) -> "Settings":
        # Absent, empty and blank are the same: the backend does not start without Entra.
        missing = [
            variable
            for variable, value in (("ENTRA_TENANT_ID", self._entra_tenant), ("ENTRA_CLIENT_ID", self._entra_client))
            if not value
        ]
        if missing:
            raise ValueError(f"Entra is not configured: set {' and '.join(missing)} in .env")
        return self

    @model_validator(mode="after")
    def _test_key_only_in_development_and_test(self) -> "Settings":
        # Fails closed: the test key outside development and test stops the backend from starting.
        if self.test_issuer_public_key_file is not None and self.app_env not in _TEST_ISSUER_APP_ENVS:
            raise ValueError(
                "TEST_ISSUER_PUBLIC_KEY_FILE is set, so APP_ENV must be exactly 'development' or 'test' "
                f"(got {self.app_env!r})"
            )
        return self

    @property
    def _entra_tenant(self) -> str:
        return (self.entra_tenant_id or "").strip()

    @property
    def _entra_client(self) -> str:
        return (self.entra_client_id or "").strip()

    @property
    def token_issuers(self) -> tuple[TokenIssuer, ...]:
        """Every issuer whose tokens are accepted: Entra always, and the test issuer when its key is set
        (the validator has already required development or test)."""
        issuers = [
            TokenIssuer(
                kind="entra",
                issuer=f"{_ENTRA_AUTHORITY}/{self._entra_tenant}/v2.0",
                audience=self._entra_client,
                jwks_url=f"{_ENTRA_AUTHORITY}/{self._entra_tenant}/discovery/v2.0/keys",
                user_claim=_ENTRA_USER_CLAIM,
                required_scope=_ENTRA_REQUIRED_SCOPE,
            )
        ]
        if self.test_issuer_public_key_file is not None:
            issuers.append(
                TokenIssuer(
                    kind="entra",
                    issuer=TEST_ISSUER,
                    audience=TEST_ISSUER_AUDIENCE,
                    jwks_url=None,
                    user_claim=_ENTRA_USER_CLAIM,
                    required_scope=_ENTRA_REQUIRED_SCOPE,
                    public_key_file=self.test_issuer_public_key_file,
                )
            )
        return tuple(issuers)


@lru_cache
def get_settings() -> Settings:
    return Settings()
