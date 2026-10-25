"""Composition root: the one place where presentation wires infrastructure to interfaces.

Tests replace get_authentication_service through app.dependency_overrides,
so no other module needs to know which implementations are in use.
"""

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import Depends
from sqlalchemy.orm import Session, sessionmaker

from app.application.services.authentication_service import AuthenticationService
from app.application.services.campaign_status_service import CampaignStatusService
from app.application.services.dsp_mapping_service import DspMappingService
from app.application.services.ingestion_exception_service import IngestionExceptionService
from app.config import get_settings
from app.domain.exceptions import DspNotConfiguredError
from app.domain.services.dsp_delivery_client import DspDeliveryClient
from app.infrastructure.auth.cognito_token_verifier import CognitoTokenVerifier
from app.infrastructure.dsp.adform_delivery_client import AdformDeliveryClient
from app.infrastructure.persistence.database import build_engine, build_session_factory
from app.infrastructure.persistence.repositories.sqlalchemy_campaign_status_repository import (
    SqlAlchemyCampaignStatusRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_exception_queue_repository import (
    SqlAlchemyExceptionQueueRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_dsp_mapping_repository import (
    SqlAlchemyDspMappingRepository,
)
from app.infrastructure.persistence.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return build_session_factory(build_engine(get_settings().database_url))


@lru_cache
def _token_verifier() -> CognitoTokenVerifier:
    # One instance per process, so the JWKS is fetched once and cached, not per request.
    settings = get_settings()
    return CognitoTokenVerifier(
        region=settings.cognito_region,
        user_pool_id=settings.cognito_user_pool_id,
        client_id=settings.cognito_client_id,
    )


def get_db_session() -> Iterator[Session]:
    with _session_factory()() as session:
        yield session


def get_authentication_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> AuthenticationService:
    return AuthenticationService(
        token_verifier=_token_verifier(),
        user_repository=SqlAlchemyUserRepository(session),
    )


@lru_cache
def _dsp_http_client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(30.0))


# A request must not wait minutes for a report: ten polls at three seconds, then the DSP counts as unreachable.
_REQUEST_PATH_MAX_POLL_ATTEMPTS = 10


def get_dsp_client_resolver() -> Callable[[str], DspDeliveryClient | None]:
    """Maps a DSP name to its connector, or None when it has none yet."""
    settings = get_settings()

    def resolve(dsp_name: str) -> DspDeliveryClient | None:
        if dsp_name != "Adform":
            return None
        if not settings.adform_client_id or settings.adform_client_secret is None:
            raise DspNotConfiguredError("Adform credentials are not configured")
        return AdformDeliveryClient(
            client_id=settings.adform_client_id,
            client_secret=settings.adform_client_secret,
            http_client=_dsp_http_client(),
            max_poll_attempts=_REQUEST_PATH_MAX_POLL_ATTEMPTS,
        )

    return resolve


def get_dsp_mapping_service(
    session: Annotated[Session, Depends(get_db_session)],
    resolver: Annotated[Callable[[str], DspDeliveryClient | None], Depends(get_dsp_client_resolver)],
) -> DspMappingService:
    return DspMappingService(
        repository=SqlAlchemyDspMappingRepository(session),
        client_for_dsp=resolver,
        clock=lambda: datetime.now(UTC).replace(tzinfo=None),
    )


def get_ingestion_exception_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> IngestionExceptionService:
    return IngestionExceptionService(
        queue=SqlAlchemyExceptionQueueRepository(session),
        clock=lambda: datetime.now(UTC).replace(tzinfo=None),
    )


def get_today() -> date:
    """The day the request is made (D). A dependency so tests can pin it."""
    return datetime.now(UTC).date()


def get_campaign_status_service(
    session: Annotated[Session, Depends(get_db_session)],
    today: Annotated[date, Depends(get_today)],
) -> CampaignStatusService:
    return CampaignStatusService(repository=SqlAlchemyCampaignStatusRepository(session), today=lambda: today)
