"""A campaign line declares its volume commitment: committed by default, or target."""

import pytest
from sqlalchemy import Engine, String, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.campaign import CampaignLineRecord
from tests.fixtures.delivery_data import insert_campaign_line


def test_the_column_is_a_not_null_string_defaulting_to_committed() -> None:
    column = CampaignLineRecord.__table__.c.volume_commitment

    assert isinstance(column.type, String)
    assert column.nullable is False
    assert str(column.server_default.arg) == "'committed'"


def test_a_line_stored_without_a_commitment_is_committed(rolled_back_session: Session) -> None:
    line_id = insert_campaign_line(rolled_back_session)
    rolled_back_session.expire_all()

    stored = rolled_back_session.scalars(
        select(CampaignLineRecord.volume_commitment).where(CampaignLineRecord.id == line_id)
    ).one()

    assert stored == "committed"


@pytest.mark.parametrize("commitment", ["committed", "target"])
def test_the_two_commitments_are_accepted(rolled_back_session: Session, commitment: str) -> None:
    line_id = insert_campaign_line(rolled_back_session)
    rolled_back_session.execute(
        text("UPDATE campaign_lines SET volume_commitment = :value WHERE id = :id"), {"value": commitment, "id": line_id}
    )
    rolled_back_session.expire_all()

    stored = rolled_back_session.scalars(
        select(CampaignLineRecord.volume_commitment).where(CampaignLineRecord.id == line_id)
    ).one()

    assert stored == commitment


@pytest.mark.parametrize("commitment", ["maybe", "Target", ""])
def test_any_other_commitment_is_refused_by_the_database(rolled_back_session: Session, commitment: str) -> None:
    line_id = insert_campaign_line(rolled_back_session)

    with pytest.raises(IntegrityError, match="volume_commitment"):
        rolled_back_session.execute(
            text("UPDATE campaign_lines SET volume_commitment = :value WHERE id = :id"),
            {"value": commitment, "id": line_id},
        )


def test_a_null_commitment_is_refused_by_the_database(rolled_back_session: Session) -> None:
    line_id = insert_campaign_line(rolled_back_session)

    with pytest.raises(IntegrityError):
        rolled_back_session.execute(
            text("UPDATE campaign_lines SET volume_commitment = NULL WHERE id = :id"), {"id": line_id}
        )


def test_the_schema_holds_the_check_constraint(test_engine: Engine) -> None:
    checks = [check["name"] for check in inspect(test_engine).get_check_constraints("campaign_lines")]

    assert "ck_campaign_lines_volume_commitment" in checks
