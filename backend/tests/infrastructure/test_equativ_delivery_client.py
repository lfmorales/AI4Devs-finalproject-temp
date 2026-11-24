"""The Equativ client: one asynchronous report per run, its wait, its paginated preview and the reading of each row."""

from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.domain.exceptions import (
    DspAuthenticationError,
    DspNotSupportedError,
    DspReportFailedError,
    DspReportTimeoutError,
    DspResponseFormatError,
    DspUnreachableError,
)
from app.domain.value_objects.delivery import DeliveryDateRange, DspDeliveryRow, ExternalLineKey, LineCatalogInfo
from app.infrastructure.dsp.equativ_delivery_client import EquativDeliveryClient
from tests.fixtures.fake_equativ import (
    DIMENSIONS,
    DOWNLOAD_URL,
    METRICS,
    REPORT_ID,
    SUCCESS,
    TOKEN_VALUE,
    FakeEquativ,
    many_rows,
    package_row,
)

WINDOW = DeliveryDateRange(date(2026, 11, 17), date(2026, 11, 23))
CLIENT_ID = "synthetic-equativ-client-id"
SECRET = "synthetic-equativ-client-secret"


class _Clock:
    """A monotonic clock that only moves when the client sleeps, so no test waits."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _client(fake: FakeEquativ, clock: _Clock | None = None) -> EquativDeliveryClient:
    clock = clock or _Clock()
    return EquativDeliveryClient(
        CLIENT_ID, SECRET, fake.client(), poll_interval_seconds=30, max_wait_seconds=900,
        sleep=clock.sleep, monotonic=clock.monotonic,
    )


def _rows(fake: FakeEquativ, clock: _Clock | None = None) -> list[DspDeliveryRow]:
    return list(_client(fake, clock).fetch_delivery(WINDOW))


# --- 3.2: one token request and one report for the run ------------------------------------------------------------


def test_one_run_sends_one_token_request_with_the_client_credentials() -> None:
    fake = FakeEquativ(rows=[package_row()])

    _rows(fake)

    assert fake.token_requests() == [
        {"grant_type": ["client_credentials"], "client_id": [CLIENT_ID], "client_secret": [SECRET]}
    ]


def test_one_run_creates_one_report_for_the_window_in_utc_with_an_exclusive_end() -> None:
    fake = FakeEquativ(rows=[package_row()])

    _rows(fake)

    (report,) = fake.created_reports()
    assert report["startDate"] == "2026-11-17T00:00:00.000Z"
    assert report["endDate"] == "2026-11-24T00:00:00.000Z"
    assert (report["timezone"], report["useCaseId"]) == ("Etc/UTC", "RTB")
    assert report["name"] == "adops360-2026-11-17-2026-11-23"


def test_the_report_asks_for_the_three_dimensions_and_the_eight_metrics_with_no_filter() -> None:
    fake = FakeEquativ(rows=[package_row()])

    _rows(fake)

    (report,) = fake.created_reports()
    assert [d["field"] for d in report["dimensions"]] == DIMENSIONS
    assert [m["field"] for m in report["metrics"]] == METRICS
    assert all(item["outputName"] == item["field"] for item in [*report["dimensions"], *report["metrics"]])
    assert report["filters"] == []


def test_the_report_carries_no_scheduling_and_no_post_processing_so_equativ_sends_no_email_and_writes_no_file() -> None:
    fake = FakeEquativ(rows=[package_row()])

    _rows(fake)

    (report,) = fake.created_reports()
    assert "scheduling" not in report
    assert "postProcessingConfiguration" not in report


def test_every_api_request_carries_the_bearer_token() -> None:
    fake = FakeEquativ(rows=[package_row()])

    _rows(fake)

    api_requests = [r for r in fake.requests if r.url.host == "demand-api.eqtv.io"]
    assert api_requests
    assert {r.headers["Authorization"] for r in api_requests} == {f"Bearer {TOKEN_VALUE}"}


def test_the_client_hands_back_the_report_id_for_the_batch_source() -> None:
    client = _client(FakeEquativ(rows=[package_row()]))
    assert client.last_report_id is None

    list(client.fetch_delivery(WINDOW))

    assert client.last_report_id == REPORT_ID


@pytest.mark.parametrize(
    ("fake", "error"),
    [
        (FakeEquativ(token_status=401), DspAuthenticationError),
        (FakeEquativ(token_status=403), DspAuthenticationError),
        (FakeEquativ(create_status=403), DspAuthenticationError),
        (FakeEquativ(create_status=400), DspReportFailedError),
        (FakeEquativ(create_status=500), DspReportFailedError),
        (FakeEquativ(fail_with=httpx.ConnectError("no route")), DspUnreachableError),
    ],
    ids=["token-401", "token-403", "create-403", "create-400", "create-500", "unreachable"],
)
def test_a_refusal_or_an_unreachable_equativ_is_a_domain_error(fake: FakeEquativ, error: type[Exception]) -> None:
    with pytest.raises(error):
        _rows(fake)


# --- 3.3: the wait --------------------------------------------------------------------------------------------------


def test_the_preview_is_read_after_the_execution_reaches_post_processing_successful() -> None:
    fake = FakeEquativ(rows=[package_row()], statuses=["PubSubPublishSuccessful", SUCCESS])
    clock = _Clock()

    _rows(fake, clock)

    paths = [p.split("/")[-1] for p in fake.paths() if "/async-report/" in p]
    assert paths == ["executions", "executions", "preview"]
    assert clock.sleeps == [30]


def test_a_run_that_is_still_generating_keeps_waiting() -> None:
    fake = FakeEquativ(
        rows=[package_row()],
        statuses=["ReportGenerationProgressing", "PubSubPublishSuccessful", "ReportGenerationProgressing", SUCCESS],
    )
    clock = _Clock()

    assert len(_rows(fake, clock)) == 1
    assert clock.sleeps == [30, 30, 30]


@pytest.mark.parametrize("status", ["ReportGenerationFailed", "PostProcessingFailed", "Error", "Cancelled"])
def test_a_failed_execution_raises_and_reads_no_preview(status: str) -> None:
    fake = FakeEquativ(rows=[package_row()], statuses=["PubSubPublishSuccessful", status])

    with pytest.raises(DspReportFailedError):
        _rows(fake)

    assert not [p for p in fake.paths() if p.endswith("/preview")]


@pytest.mark.parametrize("statuses", [["ReportGenerationProgressing"], []], ids=["never-final", "no-execution"])
def test_no_final_status_within_fifteen_minutes_raises_a_timeout(statuses: list[str]) -> None:
    fake = FakeEquativ(rows=[package_row()], statuses=statuses)
    clock = _Clock()

    with pytest.raises(DspReportTimeoutError):
        _rows(fake, clock)

    assert sum(clock.sleeps) <= 900
    assert clock.now >= 870
    assert not [p for p in fake.paths() if p.endswith("/preview")]


# --- 3.4: the preview -----------------------------------------------------------------------------------------------


def test_every_page_of_the_preview_is_read_in_pages_of_one_hundred() -> None:
    fake = FakeEquativ(rows=many_rows(238))

    rows = _rows(fake)

    assert len(rows) == 238
    assert fake.preview_pages() == [(0, 100), (100, 100), (200, 100)]


def test_a_preview_that_yields_fewer_rows_than_its_total_fails_the_run() -> None:
    fake = FakeEquativ(rows=many_rows(238), total_rows=240)

    with pytest.raises(DspResponseFormatError):
        _rows(fake)


def test_a_preview_that_is_not_ready_fails_the_run() -> None:
    fake = FakeEquativ(rows=[package_row()], preview_status="PENDING")

    with pytest.raises(DspResponseFormatError):
        _rows(fake)


def test_the_download_link_is_never_requested() -> None:
    fake = FakeEquativ(rows=many_rows(12))

    _rows(fake)

    assert DOWNLOAD_URL not in [str(r.url) for r in fake.requests]
    assert {r.url.host for r in fake.requests} == {"oauth.smartadserverapis.com", "demand-api.eqtv.io"}


def test_a_report_without_rows_yields_nothing() -> None:
    assert _rows(FakeEquativ(rows=[])) == []


# --- 3.5: one row ---------------------------------------------------------------------------------------------------


def test_the_worked_row_becomes_one_day_of_one_package_with_exact_amounts() -> None:
    (row,) = _rows(FakeEquativ(rows=[package_row()]))

    assert row.key == ExternalLineKey("900000001", "900000001")
    assert row.delivery_date == date(2026, 11, 19)
    assert (row.impressions, row.clicks, row.viewable_impressions, row.video_completions) == (61628, 12, 50111, 0)
    assert (row.buyer_spend, row.reported_revenue) == (Decimal("338.954"), Decimal("271.1632"))
    assert (row.third_party_data_cost, row.audience_data_cost) == (Decimal(0), Decimal(0))


def test_equativ_reports_no_media_cost_no_measurable_impressions_and_no_ots() -> None:
    (row,) = _rows(FakeEquativ(rows=[package_row()]))

    assert (row.media_cost, row.measurable_impressions, row.ots) == (Decimal(0), 0, Decimal(0))
    assert (row.banner_size, row.screen, row.line_format) == (None, None, None)


def test_the_data_costs_are_read_separately() -> None:
    (row,) = _rows(FakeEquativ(rows=[package_row(third_party="0", audience="1.25")]))

    assert (row.third_party_data_cost, row.audience_data_cost) == (Decimal(0), Decimal("1.25"))


def test_the_package_name_is_kept_as_reported_for_the_catalogue() -> None:
    name = "Synthetic​ Package"
    (row,) = _rows(FakeEquativ(rows=[package_row(name=name)]))

    assert row.catalog == LineCatalogInfo(name, name, None, None)


@pytest.mark.parametrize("package_id", ["0", ""])
def test_a_row_without_a_package_is_unattributed(package_id: str) -> None:
    (row,) = _rows(FakeEquativ(rows=[package_row(package_id=package_id)]))

    assert row.key is None
    assert row.catalog is None


@pytest.mark.parametrize(
    ("overrides", "column", "value"),
    [
        ({"spend": "n/a"}, "companyCurrencySpend", "n/a"),
        ({"revenue": "NaN"}, "paidBuyerConnectCompanyVendorCostCompanyCurrency", "NaN"),
        ({"impressions": ""}, "impressions", None),
        ({"impressions": "61628.5"}, "impressions", "61628.5"),
        ({"day": "19/11/2026"}, "day", "19/11/2026"),
    ],
    ids=["text-amount", "nan-amount", "empty-count", "decimal-count", "bad-day"],
)
def test_an_unreadable_value_fails_naming_the_column_and_not_the_value(
    overrides: dict[str, str], column: str, value: str | None
) -> None:
    fake = FakeEquativ(rows=[package_row(**overrides)])

    with pytest.raises(DspResponseFormatError) as failure:
        _rows(fake)

    assert column in str(failure.value)
    if value:
        assert value not in str(failure.value)


def test_a_missing_column_fails_naming_it() -> None:
    fake = FakeEquativ(rows=[package_row()], columns=[c for c in [*DIMENSIONS, *METRICS] if c != "videoComplete"])

    with pytest.raises(DspResponseFormatError, match="videoComplete"):
        _rows(fake)


def test_equativ_identifiers_are_never_resolved_by_the_dsp() -> None:
    fake = FakeEquativ()

    with pytest.raises(DspNotSupportedError):
        _client(fake).resolve_identifiers("900000001", "900000001")

    assert fake.requests == []


# --- The batch source: named as soon as the report exists -----------------------------------------------------------


def test_the_report_id_is_handed_over_as_soon_as_the_report_is_created_before_the_wait() -> None:
    fake = FakeEquativ(rows=[package_row()])
    client = _client(fake)
    handed_over: list[tuple[str, list[str]]] = []
    client.on_source_known(lambda source: handed_over.append((source, fake.paths())))

    list(client.fetch_delivery(WINDOW))

    assert handed_over == [(REPORT_ID, ["POST oauth.smartadserverapis.com/oauth2/token", "POST demand-api.eqtv.io/async-report"])]


@pytest.mark.parametrize(
    "fake",
    [
        FakeEquativ(rows=[package_row()], statuses=["PubSubPublishSuccessful", "ReportGenerationFailed"]),
        FakeEquativ(rows=many_rows(3), total_rows=5),
    ],
    ids=["failed-wait", "short-preview"],
)
def test_the_report_id_is_known_when_the_run_fails_after_the_report_was_created(fake: FakeEquativ) -> None:
    client = _client(fake)
    handed_over: list[str] = []
    client.on_source_known(handed_over.append)

    with pytest.raises((DspReportFailedError, DspResponseFormatError)):
        list(client.fetch_delivery(WINDOW))

    assert handed_over == [REPORT_ID]
    assert client.last_report_id == REPORT_ID


def test_no_source_is_named_when_the_report_is_never_created() -> None:
    client = _client(FakeEquativ(create_status=500))
    handed_over: list[str] = []
    client.on_source_known(handed_over.append)

    with pytest.raises(DspReportFailedError):
        list(client.fetch_delivery(WINDOW))

    assert handed_over == []
    assert client.last_report_id is None
