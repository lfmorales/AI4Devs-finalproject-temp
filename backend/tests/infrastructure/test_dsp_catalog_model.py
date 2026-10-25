"""The DSP line catalogue table: one row per DSP and identifier pair, the pair kept as text."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.infrastructure.persistence.models.dsp_catalog import DspCatalogLineRecord
from tests.fixtures.delivery_data import seeded_dsp_id


def _line(dsp_id: int, campaign: str = "100", line_item: str = "200") -> DspCatalogLineRecord:
    return DspCatalogLineRecord(
        dsp_id=dsp_id, external_campaign_id=campaign, external_line_item_id=line_item,
        campaign_name="Synthetic Campaign", line_item_name="Synthetic Line",
        line_start_date=date(2026, 7, 1), line_end_date=date(2026, 9, 30),
        first_seen_date=date(2026, 8, 1), last_seen_date=date(2026, 8, 9),
    )


def test_a_catalogue_line_is_stored_with_a_null_last_impressions_date(rolled_back_session):
    dsp_id = seeded_dsp_id(rolled_back_session)
    rolled_back_session.add(_line(dsp_id))
    rolled_back_session.flush()

    stored = rolled_back_session.query(DspCatalogLineRecord).one()

    assert (stored.external_campaign_id, stored.external_line_item_id) == ("100", "200")
    assert stored.last_impressions_date is None


def test_the_same_pair_twice_for_one_dsp_is_refused(rolled_back_session):
    dsp_id = seeded_dsp_id(rolled_back_session)
    rolled_back_session.add_all([_line(dsp_id), _line(dsp_id)])

    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_the_same_pair_is_allowed_under_another_campaign_or_line_item(rolled_back_session):
    dsp_id = seeded_dsp_id(rolled_back_session)
    rolled_back_session.add_all([_line(dsp_id), _line(dsp_id, campaign="101"), _line(dsp_id, line_item="201")])

    rolled_back_session.flush()
