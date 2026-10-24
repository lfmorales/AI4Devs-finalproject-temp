"""Constraints on ingestion batches and ingestion exceptions."""

from datetime import datetime

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.infrastructure.persistence.models.delivery import (
    IngestionBatchRecord,
    IngestionExceptionRecord,
)
from tests.fixtures.delivery_data import insert_campaign_line, insert_ingestion_batch, seeded_dsp_id


def _batch(dsp_id: int, **overrides: object) -> IngestionBatchRecord:
    fields: dict[str, object] = {
        "dsp_id": dsp_id,
        "route": "api",
        "source_file": None,
        "started_at": datetime(2026, 8, 4, 2, 0),
        "finished_at": None,
        "status": "running",
        "row_count": 0,
    }
    fields.update(overrides)
    return IngestionBatchRecord(**fields)


def _exception(batch_id: int, **overrides: object) -> IngestionExceptionRecord:
    fields: dict[str, object] = {
        "ingestion_batch_id": batch_id,
        "campaign_line_id": None,
        "exception_type": "delivery_without_line",
        "external_key": "adform-line-item-123",
    }
    fields.update(overrides)
    return IngestionExceptionRecord(**fields)


@pytest.mark.parametrize("route", ["api", "upload", "email"])
def test_batch_accepts_every_route(rolled_back_session, route):
    batch_id = insert_ingestion_batch(rolled_back_session, route=route)

    assert rolled_back_session.get(IngestionBatchRecord, batch_id).route == route


def test_batch_rejects_an_unknown_route(rolled_back_session):
    dsp_id = seeded_dsp_id(rolled_back_session)

    rolled_back_session.add(_batch(dsp_id, route="carrier_pigeon"))
    with pytest.raises(DBAPIError):
        rolled_back_session.flush()


def test_batch_must_reference_an_existing_dsp(rolled_back_session):
    rolled_back_session.add(_batch(dsp_id=0))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_batch_records_the_uploaded_source_file(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session, route="upload")
    batch = rolled_back_session.get(IngestionBatchRecord, batch_id)
    batch.source_file = "adform_2026-08-03.xlsx"
    rolled_back_session.flush()
    rolled_back_session.expire_all()

    assert rolled_back_session.get(IngestionBatchRecord, batch_id).source_file == "adform_2026-08-03.xlsx"


def test_exception_defaults_to_open(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)
    exception = _exception(batch_id)
    rolled_back_session.add(exception)
    rolled_back_session.flush()
    rolled_back_session.expire_all()

    assert rolled_back_session.get(IngestionExceptionRecord, exception.id).status == "open"


def test_delivery_without_line_exception_has_no_campaign_line(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)
    exception = _exception(batch_id, campaign_line_id=None)
    rolled_back_session.add(exception)
    rolled_back_session.flush()

    assert exception.campaign_line_id is None


def test_line_without_delivery_exception_references_its_line(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    batch_id = insert_ingestion_batch(rolled_back_session)
    exception = _exception(batch_id, campaign_line_id=line_id, exception_type="line_without_delivery")
    rolled_back_session.add(exception)
    rolled_back_session.flush()

    assert exception.campaign_line_id == line_id


def test_exception_requires_an_external_key(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)

    rolled_back_session.add(_exception(batch_id, external_key=None))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_exception_rejects_an_unknown_type(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)

    rolled_back_session.add(_exception(batch_id, exception_type="mystery"))
    with pytest.raises(DBAPIError):
        rolled_back_session.flush()


def test_exception_must_reference_an_existing_batch(rolled_back_session):
    rolled_back_session.add(_exception(batch_id=0))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()
