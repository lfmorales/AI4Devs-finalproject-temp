from fastapi import FastAPI

from app.presentation.errors import register_exception_handlers
from app.presentation.routers import (
    campaign_lines,
    campaign_status,
    campaigns,
    dsp_catalog,
    dsp_mappings,
    flight_preview,
    health,
    ingestion_exceptions,
    masters,
)


def create_app() -> FastAPI:
    # Settings are read lazily by the dependencies, so the app can be built without
    # the full environment (tests, OpenAPI generation).
    app = FastAPI(title="AdOps360 API", version="0.1.0")
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
    return app


app = create_app()
