"""The catalogue upsert against PostgreSQL follows the same merge rule as the in-memory one."""

from datetime import date

from sqlalchemy import select

from app.domain.value_objects.catalog import CatalogLineObservation
from app.domain.value_objects.delivery import ExternalLineKey
from app.infrastructure.persistence.models.dsp_catalog import DspCatalogLineRecord
from app.infrastructure.persistence.repositories.sqlalchemy_dsp_catalog_repository import (
    SqlAlchemyDspCatalogRepository,
)
from tests.fixtures.delivery_data import seeded_dsp_id

KEY = ExternalLineKey("100", "200")


def _observation(name: str, first: int, last: int, impressions: int | None) -> CatalogLineObservation:
    return CatalogLineObservation(
        key=KEY, campaign_name="Synthetic Campaign", line_item_name=name,
        line_start_date=date(2026, 7, 1), line_end_date=date(2026, 9, 30),
        first_seen_date=date(2026, 8, first), last_seen_date=date(2026, 8, last),
        last_impressions_date=None if impressions is None else date(2026, 8, impressions),
    )


def _stored(session) -> DspCatalogLineRecord:
    return session.scalars(select(DspCatalogLineRecord)).one()


def test_a_new_pair_is_inserted_and_a_repeat_changes_nothing(rolled_back_session):
    repository = SqlAlchemyDspCatalogRepository(rolled_back_session)
    dsp_id = seeded_dsp_id(rolled_back_session)

    repository.upsert_all(dsp_id, [_observation("Line", 4, 6, 6)])
    repository.upsert_all(dsp_id, [_observation("Line", 4, 6, 6)])

    stored = _stored(rolled_back_session)
    assert (stored.line_item_name, stored.first_seen_date, stored.last_seen_date, stored.last_impressions_date) == (
        "Line", date(2026, 8, 4), date(2026, 8, 6), date(2026, 8, 6))


def test_a_newer_observation_renames_and_widens_and_a_null_impressions_date_keeps_the_old_one(rolled_back_session):
    repository = SqlAlchemyDspCatalogRepository(rolled_back_session)
    dsp_id = seeded_dsp_id(rolled_back_session)
    repository.upsert_all(dsp_id, [_observation("Old", 4, 6, 5)])

    repository.upsert_all(dsp_id, [_observation("New", 7, 9, None)])

    stored = _stored(rolled_back_session)
    assert (stored.line_item_name, stored.first_seen_date, stored.last_seen_date, stored.last_impressions_date) == (
        "New", date(2026, 8, 4), date(2026, 8, 9), date(2026, 8, 5))


def test_an_older_observation_widens_the_dates_but_keeps_the_newer_name(rolled_back_session):
    repository = SqlAlchemyDspCatalogRepository(rolled_back_session)
    dsp_id = seeded_dsp_id(rolled_back_session)
    repository.upsert_all(dsp_id, [_observation("Current", 7, 9, 9)])

    repository.upsert_all(dsp_id, [_observation("Stale", 2, 4, 4)])

    stored = _stored(rolled_back_session)
    assert (stored.line_item_name, stored.first_seen_date, stored.last_seen_date, stored.last_impressions_date) == (
        "Current", date(2026, 8, 2), date(2026, 8, 9), date(2026, 8, 9))
