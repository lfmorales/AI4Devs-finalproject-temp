"""Creating a mapping checks the pair with the DSP: found, unknown and unreachable are three outcomes."""

from collections.abc import Callable
from datetime import date, datetime

import pytest

from app.application.services.dsp_mapping_service import DspMappingService, IdentifierCheck
from app.domain.entities.dsp_catalog import CatalogPage, CatalogQuery
from app.domain.entities.dsp_mapping import LineDsp
from app.domain.exceptions import (
    CampaignLineNotFoundError,
    DspAuthenticationError,
    DspNotSupportedError,
    DspReportTimeoutError,
    DspUnreachableError,
    DuplicateDspMappingError,
    InvalidEquativPackageError,
)
from app.domain.repositories.dsp_catalog_query_repository import DspCatalogQueryRepository
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
    service, repository = _service(None, lines={LINE: LineDsp(dsp_id=3, dsp_name="Displayce")})

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


# --- An Equativ mapping is validated by the user who writes the package id ------------------------------------------

EQUATIV = LineDsp(dsp_id=2, dsp_name="Equativ", line_start_date=date(2026, 11, 1))
PACKAGE = "900000001"


class _Catalog(DspCatalogQueryRepository):
    """A catalogue that knows one Equativ package and records every question."""

    def __init__(self) -> None:
        self.questions: list[tuple[int, ExternalLineKey]] = []

    def search(self, query: CatalogQuery) -> CatalogPage:
        raise AssertionError("a mapping never searches the catalogue")

    def find_last_impressions_date(self, dsp_id: int, key: ExternalLineKey) -> date | None:
        self.questions.append((dsp_id, key))
        return date(2026, 11, 19) if key == ExternalLineKey(PACKAGE, PACKAGE) else None


def _never_asked(dsp_name: str) -> DspDeliveryClient | None:
    raise AssertionError(f"no client is asked for {dsp_name}")


def _equativ_service(
    client_for_dsp: Callable[[str], DspDeliveryClient | None] = _never_asked,
) -> tuple[DspMappingService, InMemoryDspMappingRepository, _Catalog]:
    repository = InMemoryDspMappingRepository({LINE: EQUATIV, OTHER_LINE: ADFORM})
    catalog = _Catalog()
    service = DspMappingService(
        repository, client_for_dsp, lambda: NOW, catalog=catalog, today=lambda: date(2026, 11, 24),
        user_validated_dsps=frozenset({"Equativ"}),
    )
    return service, repository, catalog


def test_an_equativ_package_written_by_operations_is_validated_by_the_user_asking_no_client() -> None:
    service, repository, _ = _equativ_service()

    result = service.create_mapping(LINE, PACKAGE, PACKAGE)

    assert result.check is IdentifierCheck.USER_VALIDATED
    assert (result.mapping.key, result.mapping.validated_at) == (ExternalLineKey(PACKAGE, PACKAGE), NOW)
    assert result.last_impressions_date == date(2026, 11, 19)
    assert len(repository.mappings) == 1


def test_an_equativ_package_not_in_the_catalogue_is_validated_all_the_same() -> None:
    service, repository, catalog = _equativ_service()

    result = service.create_mapping(LINE, "900000002", "900000002")

    assert (result.check, result.mapping.validated_at) == (IdentifierCheck.USER_VALIDATED, NOW)
    assert result.last_impressions_date is None
    assert catalog.questions == [(EQUATIV.dsp_id, ExternalLineKey("900000002", "900000002"))]


def test_an_equativ_package_is_normalised_like_any_pair() -> None:
    service, _, _ = _equativ_service()

    result = service.create_mapping(LINE, f" {PACKAGE} ", f"{PACKAGE}\n")

    assert result.mapping.key == ExternalLineKey(PACKAGE, PACKAGE)


@pytest.mark.parametrize(
    ("campaign_id", "line_item_id"),
    [
        (PACKAGE, "900000002"),
        ("abc", "abc"),
        ("9000-0001", "9000-0001"),
        ("900000001.0", "900000001.0"),
        ("９００", "９００"),
        ("²", "²"),
        ("0", "0"),
        ("0900000001", "0900000001"),
    ],
    ids=["two-ids", "letters", "dash", "decimal", "full-width-digits", "superscript", "zero", "leading-zero"],
)
def test_a_malformed_equativ_pair_is_refused_and_nothing_is_stored(campaign_id: str, line_item_id: str) -> None:
    service, repository, catalog = _equativ_service()

    with pytest.raises(InvalidEquativPackageError):
        service.create_mapping(LINE, campaign_id, line_item_id)

    assert repository.mappings == []
    assert catalog.questions == []


def test_an_equativ_package_already_mapped_is_a_duplicate() -> None:
    service, _, _ = _equativ_service()
    service.create_mapping(LINE, PACKAGE, PACKAGE)

    with pytest.raises(DuplicateDspMappingError):
        service.create_mapping(LINE, PACKAGE, PACKAGE)


def test_an_adform_mapping_is_still_checked_with_adform_when_equativ_is_validated_by_the_user() -> None:
    asked: list[str] = []
    adform = InMemoryDspDeliveryClient([], known_keys=[KNOWN])

    def client_for_dsp(dsp_name: str) -> DspDeliveryClient | None:
        asked.append(dsp_name)
        return adform if dsp_name == "Adform" else None

    service, _, _ = _equativ_service(client_for_dsp)

    result = service.create_mapping(OTHER_LINE, "1001", "2001")

    assert (result.check, asked) == (IdentifierCheck.FOUND, ["Adform"])
