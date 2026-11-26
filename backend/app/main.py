from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.presentation.dependencies.providers import build_startup_configuration
from app.presentation.errors import register_exception_handlers
from app.presentation.routers import (
    billing,
    campaign_lines,
    campaign_status,
    campaigns,
    carryover,
    dsp_catalog,
    dsp_mappings,
    flight_preview,
    health,
    ingestion_exceptions,
    margin,
    masters,
    users,
)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Settings, the issuer list and the verifiers are built when the server starts, so an invalid or
    # incomplete configuration stops the backend here instead of failing on the first request.
    build_startup_configuration()
    yield


def create_app() -> FastAPI:
    # Building the app reads no setting: only starting it does (the lifespan above), so the app can
    # still be built without the full environment (tests, OpenAPI generation).
    app = FastAPI(title="AdOps360 API", version="0.1.0", lifespan=_lifespan)
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(campaigns.router)
    app.include_router(masters.router)
    app.include_router(dsp_mappings.router)
    app.include_router(dsp_catalog.router)
    app.include_router(campaign_lines.router)
    app.include_router(ingestion_exceptions.router)
    app.include_router(flight_preview.router)
    app.include_router(campaign_status.router)
    app.include_router(margin.router)
    app.include_router(billing.router)
    app.include_router(carryover.router)
    app.include_router(users.router)
    return app


app = create_app()
