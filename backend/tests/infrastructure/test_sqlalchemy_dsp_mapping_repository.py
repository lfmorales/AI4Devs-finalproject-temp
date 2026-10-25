from datetime import date, datetime

import pytest
from sqlalchemy import select

from app.domain.entities.dsp_mapping import LineDsp
from app.domain.exceptions import DuplicateDspMappingError
from app.domain.value_objects.delivery import ExternalLineKey
from app.infrastructure.persistence.models.dsp_mapping import DSPMappingRecord
from app.infrastructure.persistence.repositories.sqlalchemy_dsp_mapping_repository import (
    SqlAlchemyDspMappingRepository,
)
from tests.fixtures.delivery_data import insert_campaign_line, seeded_dsp_id

KEY = ExternalLineKey("1001", "2001")
VALIDATED_AT = datetime(2026, 8, 10, 9, 0)


def test_the_dsp_of_a_line_is_read_with_its_name(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)

    line_dsp = SqlAlchemyDspMappingRepository(rolled_back_session).get_line_dsp(line_id)

    assert line_dsp == LineDsp(
        dsp_id=seeded_dsp_id(rolled_back_session), dsp_name="Delivery fixture DSP", line_start_date=date(2026, 8, 1))


def test_a_missing_line_has_no_dsp(rolled_back_session):
    assert SqlAlchemyDspMappingRepository(rolled_back_session).get_line_dsp(0) is None


def test_a_mapping_is_stored_with_text_identifiers_and_its_validation_time(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)
    dsp_id = seeded_dsp_id(rolled_back_session)
    repository = SqlAlchemyDspMappingRepository(rolled_back_session)

    mapping = repository.add(line_id, dsp_id, KEY, VALIDATED_AT)

    record = rolled_back_session.scalars(select(DSPMappingRecord)).one()
    assert (record.id, record.external_campaign_id, record.external_line_item_id, record.validated_at) == (
        mapping.id, "1001", "2001", VALIDATED_AT)
    assert repository.pair_exists(dsp_id, KEY) is True


def test_an_unvalidated_mapping_has_no_validation_time(rolled_back_session):
    line_id = insert_campaign_line(rolled_back_session)

    mapping = SqlAlchemyDspMappingRepository(rolled_back_session).add(
        line_id, seeded_dsp_id(rolled_back_session), KEY, None)

    assert mapping.validated_at is None


def test_a_pair_never_mapped_does_not_exist(rolled_back_session):
    assert SqlAlchemyDspMappingRepository(rolled_back_session).pair_exists(seeded_dsp_id(rolled_back_session), KEY) is False


def test_adding_a_pair_that_was_mapped_in_the_meantime_is_a_domain_error(rolled_back_session):
    first = insert_campaign_line(rolled_back_session, "First mapped campaign")
    second = insert_campaign_line(rolled_back_session, "Second mapped campaign")
    dsp_id = seeded_dsp_id(rolled_back_session)
    repository = SqlAlchemyDspMappingRepository(rolled_back_session)
    repository.add(first, dsp_id, KEY, None)

    with pytest.raises(DuplicateDspMappingError):
        repository.add(second, dsp_id, KEY, None)


def test_an_integrity_error_that_is_not_the_pair_constraint_is_not_reported_as_a_duplicate(rolled_back_session):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        SqlAlchemyDspMappingRepository(rolled_back_session).add(0, seeded_dsp_id(rolled_back_session), KEY, None)
