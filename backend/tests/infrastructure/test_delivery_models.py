"""The delivery table: exact money, and delivered volume kept apart from contracted volume."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import Numeric, inspect, select
from sqlalchemy.exc import IntegrityError

from app.infrastructure.persistence.models.campaign import CampaignLineRecord
from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord
from tests.fixtures.delivery_data import (
    CONTRACTED_IMPRESSIONS,
    insert_campaign_line,
    insert_ingestion_batch,
)


def _delivery(campaign_line_id: int, ingestion_batch_id: int, **overrides: object) -> DailyDeliveryRecord:
    fields: dict[str, object] = {
        "campaign_line_id": campaign_line_id,
        "ingestion_batch_id": ingestion_batch_id,
        "delivery_date": date(2026, 8, 3),
        "impressions": 1000,
        "clicks": 10,
        "media_cost": Decimal("12.3456"),
        "measurable_impressions": 900,
        "viewable_impressions": 700,
    }
    fields.update(overrides)
    return DailyDeliveryRecord(**fields)


def test_media_cost_column_is_an_exact_numeric(rolled_back_session):
    media_cost_column = DailyDeliveryRecord.__table__.c.media_cost

    assert isinstance(media_cost_column.type, Numeric)
    assert media_cost_column.type.asdecimal is True


def test_media_cost_is_stored_without_floating_point_drift(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    batch_id = insert_ingestion_batch(rolled_back_session)
    rolled_back_session.add(_delivery(line_id, batch_id, media_cost=Decimal("0.1") + Decimal("0.2")))
    rolled_back_session.flush()
    rolled_back_session.expire_all()

    stored = rolled_back_session.scalars(select(DailyDeliveryRecord.media_cost)).one()

    assert stored == Decimal("0.3")
    assert isinstance(stored, Decimal)


def test_delivered_and_contracted_volumes_are_separate_fields(rolled_back_session):
    delivery_columns = {column.name for column in inspect(DailyDeliveryRecord).columns}
    line_columns = {column.name for column in inspect(CampaignLineRecord).columns}

    assert "impressions" in delivery_columns
    assert "contracted_impressions" not in delivery_columns
    assert "contracted_impressions" in line_columns


def test_ingesting_delivery_leaves_contracted_volume_unchanged(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    batch_id = insert_ingestion_batch(rolled_back_session)

    rolled_back_session.add(_delivery(line_id, batch_id, impressions=250_000))
    rolled_back_session.flush()
    rolled_back_session.expire_all()

    line = rolled_back_session.get(CampaignLineRecord, line_id)
    assert line.contracted_impressions == CONTRACTED_IMPRESSIONS
    assert rolled_back_session.scalars(select(DailyDeliveryRecord.impressions)).one() == 250_000


def test_a_line_has_at_most_one_delivery_per_day(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    batch_id = insert_ingestion_batch(rolled_back_session)
    rolled_back_session.add(_delivery(line_id, batch_id))
    rolled_back_session.flush()

    rolled_back_session.add(_delivery(line_id, batch_id, impressions=2000))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_a_delivery_must_reference_an_ingestion_batch(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)

    rolled_back_session.add(_delivery(line_id, ingestion_batch_id=0))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_line_format_is_optional_contrast_data(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    batch_id = insert_ingestion_batch(rolled_back_session)

    rolled_back_session.add(_delivery(line_id, batch_id, line_format=None, banner_size=None, screen=None))
    rolled_back_session.flush()
