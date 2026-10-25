"""Exception types, uniqueness, resolution fields and retained delivery, enforced by PostgreSQL."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.infrastructure.persistence.models.campaign import CampaignLineRecord
from app.infrastructure.persistence.models.delivery import (
    IngestionExceptionDeliveryRecord,
    IngestionExceptionRecord,
)
from tests.fixtures.delivery_data import (
    insert_campaign_line,
    insert_ingestion_batch,
    insert_user,
    period_of_line,
    seeded_dsp_id,
)


def _period_of(session, line_id: int) -> int:
    return period_of_line(session, line_id)


def _unmatched(session, batch_id: int, **overrides: object) -> IngestionExceptionRecord:
    fields: dict[str, object] = {
        "ingestion_batch_id": batch_id,
        "exception_type": "unmatched_delivery",
        "dsp_id": seeded_dsp_id(session),
        "external_campaign_id": "1001",
        "external_line_item_id": "2001",
    }
    fields.update(overrides)
    return IngestionExceptionRecord(**fields)


def _missing(session, batch_id: int, line_id: int, **overrides: object) -> IngestionExceptionRecord:
    fields: dict[str, object] = {
        "ingestion_batch_id": batch_id,
        "exception_type": "missing_delivery",
        "campaign_line_id": line_id,
        "campaign_period_id": _period_of(session, line_id),
    }
    fields.update(overrides)
    return IngestionExceptionRecord(**fields)


@pytest.mark.parametrize("exception_type", ["unmatched_delivery", "missing_delivery", "channel_mismatch"])
def test_the_three_exception_types_exist(rolled_back_session, exception_type):
    batch_id = insert_ingestion_batch(rolled_back_session)
    line_id = insert_campaign_line(rolled_back_session)
    exception = IngestionExceptionRecord(
        ingestion_batch_id=batch_id, exception_type=exception_type, campaign_line_id=line_id,
        campaign_period_id=_period_of(rolled_back_session, line_id), dsp_id=seeded_dsp_id(rolled_back_session),
        external_campaign_id="1001", external_line_item_id="2001",
    )
    rolled_back_session.add(exception)
    rolled_back_session.flush()


@pytest.mark.parametrize("old_name", ["delivery_without_line", "line_without_delivery", "mystery"])
def test_an_unknown_or_superseded_type_is_rejected(rolled_back_session, old_name):
    batch_id = insert_ingestion_batch(rolled_back_session)

    rolled_back_session.add(_unmatched(rolled_back_session, batch_id, exception_type=old_name))
    with pytest.raises(DBAPIError):
        rolled_back_session.flush()


def test_an_exception_defaults_to_open_and_unresolved(rolled_back_session):
    exception = _unmatched(rolled_back_session, insert_ingestion_batch(rolled_back_session))
    rolled_back_session.add(exception)
    rolled_back_session.flush()
    rolled_back_session.expire_all()

    stored = rolled_back_session.get(IngestionExceptionRecord, exception.id)
    assert (stored.status, stored.resolved_at, stored.resolved_by, stored.note) == ("open", None, None, None)


def test_an_unmatched_exception_needs_its_dsp_and_pair(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)

    rolled_back_session.add(_unmatched(rolled_back_session, batch_id, external_line_item_id=None))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_a_missing_delivery_exception_needs_its_line_and_period(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)
    line_id = insert_campaign_line(rolled_back_session)

    rolled_back_session.add(_missing(rolled_back_session, batch_id, line_id, campaign_period_id=None))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_a_pair_has_one_unmatched_exception_per_dsp_whatever_its_status(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)
    user_id = insert_user(rolled_back_session)
    first = _unmatched(rolled_back_session, batch_id, status="resolved", resolved_at=datetime(2026, 8, 5),
                       resolved_by=user_id)
    rolled_back_session.add(first)
    rolled_back_session.flush()

    rolled_back_session.add(_unmatched(rolled_back_session, batch_id))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_the_same_pair_may_be_unmatched_for_another_dsp(rolled_back_session):
    from tests.fixtures.delivery_data import insert_other_dsp

    batch_id = insert_ingestion_batch(rolled_back_session)
    rolled_back_session.add(_unmatched(rolled_back_session, batch_id))
    rolled_back_session.flush()

    rolled_back_session.add(_unmatched(rolled_back_session, batch_id, dsp_id=insert_other_dsp(rolled_back_session)))
    rolled_back_session.flush()


def test_a_line_and_period_have_one_missing_delivery_exception(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)
    line_id = insert_campaign_line(rolled_back_session)
    rolled_back_session.add(_missing(rolled_back_session, batch_id, line_id))
    rolled_back_session.flush()

    rolled_back_session.add(_missing(rolled_back_session, batch_id, line_id))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_an_exception_keeps_the_first_and_last_dates_of_its_retained_delivery(rolled_back_session):
    exception = _unmatched(rolled_back_session, insert_ingestion_batch(rolled_back_session),
                           first_date=date(2026, 8, 3), last_date=date(2026, 8, 9))
    rolled_back_session.add(exception)
    rolled_back_session.flush()
    rolled_back_session.expire_all()

    stored = rolled_back_session.get(IngestionExceptionRecord, exception.id)
    assert (stored.first_date, stored.last_date) == (date(2026, 8, 3), date(2026, 8, 9))


def test_a_resolved_exception_records_when_by_whom_and_an_optional_note(rolled_back_session):
    user_id = insert_user(rolled_back_session)
    exception = _unmatched(rolled_back_session, insert_ingestion_batch(rolled_back_session), status="resolved",
                           resolved_at=datetime(2026, 8, 10, 9, 0), resolved_by=user_id, note="Typo in the DSP name")
    rolled_back_session.add(exception)
    rolled_back_session.flush()
    rolled_back_session.expire_all()

    stored = rolled_back_session.get(IngestionExceptionRecord, exception.id)
    assert (stored.resolved_at, stored.resolved_by, stored.note) == (datetime(2026, 8, 10, 9, 0), user_id,
                                                                     "Typo in the DSP name")


def test_a_resolved_exception_without_a_resolution_time_or_user_is_rejected(rolled_back_session):
    rolled_back_session.add(_unmatched(rolled_back_session, insert_ingestion_batch(rolled_back_session),
                                       status="resolved"))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_an_open_exception_with_a_resolution_time_is_rejected(rolled_back_session):
    rolled_back_session.add(_unmatched(rolled_back_session, insert_ingestion_batch(rolled_back_session),
                                       resolved_at=datetime(2026, 8, 10, 9, 0)))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_the_resolving_user_must_exist(rolled_back_session):
    rolled_back_session.add(_unmatched(rolled_back_session, insert_ingestion_batch(rolled_back_session),
                                       status="resolved", resolved_at=datetime(2026, 8, 10), resolved_by=0))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_an_exception_must_reference_an_existing_batch(rolled_back_session):
    rolled_back_session.add(_unmatched(rolled_back_session, 0))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def _retained(exception_id: int, day: date, **overrides: object) -> IngestionExceptionDeliveryRecord:
    fields: dict[str, object] = {
        "exception_id": exception_id, "delivery_date": day, "impressions": 100, "clicks": 3,
        "media_cost": Decimal("1.250000"), "measurable_impressions": 90, "viewable_impressions": 70,
    }
    fields.update(overrides)
    return IngestionExceptionDeliveryRecord(**fields)


def test_retained_delivery_is_unique_per_exception_and_date(rolled_back_session):
    exception = _unmatched(rolled_back_session, insert_ingestion_batch(rolled_back_session))
    rolled_back_session.add(exception)
    rolled_back_session.flush()
    rolled_back_session.add(_retained(exception.id, date(2026, 8, 5)))
    rolled_back_session.flush()

    rolled_back_session.add(_retained(exception.id, date(2026, 8, 5)))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_retained_delivery_keeps_six_decimals_of_cost(rolled_back_session):
    exception = _unmatched(rolled_back_session, insert_ingestion_batch(rolled_back_session))
    rolled_back_session.add(exception)
    rolled_back_session.flush()
    rolled_back_session.add(_retained(exception.id, date(2026, 8, 5), media_cost=Decimal("12.345678")))
    rolled_back_session.flush()
    rolled_back_session.expire_all()

    assert rolled_back_session.scalars(select(IngestionExceptionDeliveryRecord.media_cost)).one() == Decimal("12.345678")


def test_retained_delivery_must_belong_to_an_existing_exception(rolled_back_session):
    rolled_back_session.add(_retained(0, date(2026, 8, 5)))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()
