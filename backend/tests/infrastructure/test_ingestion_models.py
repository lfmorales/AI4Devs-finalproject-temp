"""Constraints on ingestion batches and ingestion exceptions."""

from datetime import datetime

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.infrastructure.persistence.models.delivery import IngestionBatchRecord
from tests.fixtures.delivery_data import insert_ingestion_batch, seeded_dsp_id


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


def test_batch_counts_no_ignored_rows_by_default(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)
    rolled_back_session.expire_all()

    assert rolled_back_session.get(IngestionBatchRecord, batch_id).ignored_row_count == 0


def test_batch_records_how_many_rows_were_ignored(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)
    rolled_back_session.get(IngestionBatchRecord, batch_id).ignored_row_count = 42
    rolled_back_session.flush()
    rolled_back_session.expire_all()

    assert rolled_back_session.get(IngestionBatchRecord, batch_id).ignored_row_count == 42


def test_batch_ignored_row_count_is_required(rolled_back_session):
    # Core insert, not the ORM: the ORM replaces an explicit None with the column's Python default.
    statement = insert(IngestionBatchRecord).values(
        dsp_id=seeded_dsp_id(rolled_back_session),
        route="api",
        started_at=datetime(2026, 8, 4, 2, 0),
        status="running",
        row_count=0,
        ignored_row_count=None,
    )

    with pytest.raises(IntegrityError):
        rolled_back_session.execute(statement)


def test_batch_counts_no_zero_unmatched_rows_by_default(rolled_back_session):
    batch_id = insert_ingestion_batch(rolled_back_session)
    rolled_back_session.expire_all()

    assert rolled_back_session.get(IngestionBatchRecord, batch_id).zero_unmatched_row_count == 0


def test_batch_zero_unmatched_row_count_is_required(rolled_back_session):
    statement = insert(IngestionBatchRecord).values(
        dsp_id=seeded_dsp_id(rolled_back_session),
        route="api",
        started_at=datetime(2026, 8, 4, 2, 0),
        status="running",
        row_count=0,
        zero_unmatched_row_count=None,
    )

    with pytest.raises(IntegrityError):
        rolled_back_session.execute(statement)
