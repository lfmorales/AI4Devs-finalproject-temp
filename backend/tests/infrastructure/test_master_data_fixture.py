"""The master data fixture of the integration tests carries the closed channel catalogue, with stable ids."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.masters import ChannelRecord
from tests.fixtures.master_data import seed_master_data


def test_the_fixture_loads_the_four_channels_with_ids_one_to_four(rolled_back_session: Session) -> None:
    seed_master_data(rolled_back_session)

    channels = rolled_back_session.execute(select(ChannelRecord.id, ChannelRecord.name).order_by(ChannelRecord.id)).all()

    assert [tuple(channel) for channel in channels] == [(1, "Directo"), (2, "Deal"), (3, "DOOH"), (4, "CTV")]


def test_the_fixture_gives_dooh_the_ots_metric_and_the_other_channels_impressions(rolled_back_session: Session) -> None:
    seed_master_data(rolled_back_session)

    metrics = dict(rolled_back_session.execute(select(ChannelRecord.name, ChannelRecord.delivery_metric)).tuples().all())

    assert metrics == {"Directo": "impressions", "Deal": "impressions", "DOOH": "ots", "CTV": "impressions"}
