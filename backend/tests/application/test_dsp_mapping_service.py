"""Creating a mapping checks the pair with the DSP: found, unknown and unreachable are three outcomes."""

from datetime import datetime

import pytest

from app.application.services.dsp_mapping_service import DspMappingService, IdentifierCheck
from app.domain.entities.dsp_mapping import LineDsp
from app.domain.exceptions import (
    CampaignLineNotFoundError,
    DspAuthenticationError,
    DspNotSupportedError,
    DspReportTimeoutError,
    DspUnreachableError,
    DuplicateDspMappingError,
)
from app.domain.services.dsp_delivery_client import DspDeliveryClient
from app.domain.value_objects.delivery import ExternalLineKey
from tests.fixtures.dsp_delivery_client import InMemoryDspDeliveryClient, ScriptedDspDeliveryClient
from tests.fixtures.in_memory_dsp_mapping_repository import InMemoryDspMappingRepository

NOW = datetime(2026, 8, 10, 9, 0)
LINE = 5
OTHER_LINE = 6
ADFORM = LineDsp(dsp_id=1, dsp_name="Adform")
KNOWN = ExternalLineKey("1001", "2001")


def _service(client: DspDeliveryClient | None, lines: dict[int, LineDsp] | None = None):
    repository = InMemoryDspMappingRepository(lines if lines is not None else {LINE: ADFORM, OTHER_LINE: ADFORM})
    service = DspMappingService(repository, lambda dsp_name: client if dsp_name == "Adform" else None, lambda: NOW)
    return service, repository


def test_a_found_pair_creates_a_validated_mapping():
    service, repository = _service(InMemoryDspDeliveryClient([], known_keys=[KNOWN]))

    result = service.create_mapping(LINE, "1001", "2001")

    assert result.check is IdentifierCheck.FOUND
    assert (result.mapping.validated_at, result.mapping.key, result.mapping.dsp_id) == (NOW, KNOWN, 1)
    assert repository.mappings == [result.mapping]


def test_an_unknown_pair_creates_an_unvalidated_mapping():
    service, repository = _service(InMemoryDspDeliveryClient([], known_keys=[KNOWN]))

    result = service.create_mapping(LINE, "1001", "9999")

    assert (result.check, result.mapping.validated_at) == (IdentifierCheck.UNKNOWN, None)
    assert len(repository.mappings) == 1


@pytest.mark.parametrize("failure", [DspUnreachableError("down"), DspReportTimeoutError("slow")])
def test_an_unreachable_dsp_creates_an_unvalidated_mapping(failure):
    service, repository = _service(ScriptedDspDeliveryClient(failure))

    result = service.create_mapping(LINE, "1001", "2001")

    assert (result.check, result.mapping.validated_at) == (IdentifierCheck.UNREACHABLE, None)
    assert len(repository.mappings) == 1


def test_the_three_outcomes_are_distinct():
    outcomes = {
        _service(InMemoryDspDeliveryClient([], known_keys=[KNOWN]))[0].create_mapping(LINE, "1001", "2001").check,
        _service(InMemoryDspDeliveryClient([]))[0].create_mapping(LINE, "1001", "2001").check,
        _service(ScriptedDspDeliveryClient(DspUnreachableError("down")))[0].create_mapping(LINE, "1001", "2001").check,
    }

    assert outcomes == {IdentifierCheck.FOUND, IdentifierCheck.UNKNOWN, IdentifierCheck.UNREACHABLE}


def test_another_dsp_failure_creates_nothing_and_propagates():
    service, repository = _service(ScriptedDspDeliveryClient(DspAuthenticationError("refused")))

    with pytest.raises(DspAuthenticationError):
        service.create_mapping(LINE, "1001", "2001")

    assert repository.mappings == []


def test_a_pair_already_mapped_is_rejected_without_asking_the_dsp():
    client = ScriptedDspDeliveryClient(KNOWN)
    service, repository = _service(client)
    service.create_mapping(LINE, "1001", "2001")
    questions_before = client.questions

    with pytest.raises(DuplicateDspMappingError):
        service.create_mapping(OTHER_LINE, "1001", "2001")

    assert client.questions == questions_before
    assert len(repository.mappings) == 1


def test_an_unknown_campaign_line_is_rejected():
    service, repository = _service(ScriptedDspDeliveryClient(KNOWN))

    with pytest.raises(CampaignLineNotFoundError):
        service.create_mapping(999, "1001", "2001")

    assert repository.mappings == []


def test_a_dsp_without_a_connector_is_rejected_and_nothing_is_created():
    service, repository = _service(None, lines={LINE: LineDsp(dsp_id=2, dsp_name="Equativ")})

    with pytest.raises(DspNotSupportedError):
        service.create_mapping(LINE, "1001", "2001")

    assert repository.mappings == []


def test_identifiers_are_normalised_before_they_are_checked_and_stored():
    service, _ = _service(InMemoryDspDeliveryClient([], known_keys=[KNOWN]))

    result = service.create_mapping(LINE, " 1001 ", "2001\n")

    assert (result.check, result.mapping.key) == (IdentifierCheck.FOUND, KNOWN)


def test_one_line_may_hold_several_pairs():
    service, repository = _service(ScriptedDspDeliveryClient(KNOWN))

    service.create_mapping(LINE, "1001", "2001")
    service.create_mapping(LINE, "1001", "2002")

    assert [m.campaign_line_id for m in repository.mappings] == [LINE, LINE]
