"""A channel names the unit of its volume: impressions by default, OTS for DOOH."""

import asyncio

import pytest
from sqlalchemy import Engine, String, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.masters import ChannelRecord
from app.infrastructure.persistence.repositories.master_repository import MasterRepositoryImpl


def test_the_column_is_a_not_null_string_defaulting_to_impressions() -> None:
    column = ChannelRecord.__table__.c.delivery_metric

    assert isinstance(column.type, String)
    assert column.nullable is False
    assert str(column.server_default.arg) == "'impressions'"


def test_a_channel_created_without_a_metric_counts_impressions(rolled_back_session: Session) -> None:
    rolled_back_session.add(ChannelRecord(name="Metric default"))
    rolled_back_session.flush()
    rolled_back_session.expire_all()

    stored = rolled_back_session.scalars(select(ChannelRecord).where(ChannelRecord.name == "Metric default")).one()

    assert stored.delivery_metric == "impressions"


@pytest.mark.parametrize("metric", ["impressions", "ots"])
def test_the_two_metrics_are_accepted(rolled_back_session: Session, metric: str) -> None:
    rolled_back_session.add(ChannelRecord(name="Metric accepted", delivery_metric=metric))
    rolled_back_session.flush()
    rolled_back_session.expire_all()

    stored = rolled_back_session.scalars(select(ChannelRecord).where(ChannelRecord.name == "Metric accepted")).one()

    assert stored.delivery_metric == metric


@pytest.mark.parametrize("metric", ["views", "OTS", ""])
def test_any_other_metric_is_refused_by_the_database(rolled_back_session: Session, metric: str) -> None:
    rolled_back_session.add(ChannelRecord(name="Metric refused", delivery_metric=metric))

    with pytest.raises(IntegrityError, match="delivery_metric"):
        rolled_back_session.flush()


def test_a_null_metric_is_refused_by_the_database(rolled_back_session: Session) -> None:
    with pytest.raises(IntegrityError):
        rolled_back_session.execute(text("INSERT INTO channels (name, delivery_metric) VALUES ('Metric null', NULL)"))


def test_the_schema_holds_the_check_constraint(test_engine: Engine) -> None:
    checks = [check["name"] for check in inspect(test_engine).get_check_constraints("channels")]

    assert "ck_channels_delivery_metric" in checks


def test_the_master_repository_returns_the_metric_with_the_channel(rolled_back_session: Session) -> None:
    channel = ChannelRecord(name="Metric repository", delivery_metric="ots")
    rolled_back_session.add(channel)
    rolled_back_session.flush()

    found = asyncio.run(MasterRepositoryImpl(rolled_back_session).get_channel(channel.id))

    assert found is not None
    assert (found.name, found.delivery_metric) == ("Metric repository", "ots")
