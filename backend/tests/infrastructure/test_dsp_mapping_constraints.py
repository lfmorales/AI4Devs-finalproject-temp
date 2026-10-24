"""An external identifier pair belongs to one campaign line per DSP; one line may hold several pairs."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.infrastructure.persistence.models.dsp_mapping import DSPMappingRecord
from app.infrastructure.persistence.models.masters import DSPRecord
from tests.fixtures.delivery_data import insert_campaign_line, seeded_dsp_id


def _mapping(line_id: int, dsp_id: int, campaign: str = "1001", line_item: str = "2001") -> DSPMappingRecord:
    return DSPMappingRecord(
        campaign_line_id=line_id, dsp_id=dsp_id, external_campaign_id=campaign, external_line_item_id=line_item
    )


def test_a_second_line_cannot_map_to_the_same_pair_of_the_same_dsp(rolled_back_session):
    first_line = insert_campaign_line(rolled_back_session, "First mapped campaign")
    second_line = insert_campaign_line(rolled_back_session, "Second mapped campaign")
    dsp_id = seeded_dsp_id(rolled_back_session)
    rolled_back_session.add(_mapping(first_line, dsp_id))
    rolled_back_session.flush()

    rolled_back_session.add(_mapping(second_line, dsp_id))
    with pytest.raises(IntegrityError):
        rolled_back_session.flush()


def test_the_same_pair_may_exist_for_another_dsp(rolled_back_session):
    first_line = insert_campaign_line(rolled_back_session, "First mapped campaign")
    second_line = insert_campaign_line(rolled_back_session, "Second mapped campaign")
    other_dsp = DSPRecord(name="Another DSP", is_active=True)
    rolled_back_session.add(other_dsp)
    rolled_back_session.flush()
    rolled_back_session.add(_mapping(first_line, seeded_dsp_id(rolled_back_session)))
    rolled_back_session.flush()

    rolled_back_session.add(_mapping(second_line, other_dsp.id))
    rolled_back_session.flush()


def test_one_line_may_hold_several_pairs(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    dsp_id = seeded_dsp_id(rolled_back_session)

    rolled_back_session.add_all([_mapping(line_id, dsp_id, line_item="2001"), _mapping(line_id, dsp_id, line_item="2002")])
    rolled_back_session.flush()
