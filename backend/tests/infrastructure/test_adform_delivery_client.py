"""The Adform stats client against a synthetic Adform: token, asynchronous report, parsing."""

import base64
import json
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.domain.exceptions import (
    DspAuthenticationError,
    DspReportFailedError,
    DspReportTimeoutError,
    DspResponseFormatError,
    DspUnreachableError,
    UnsupportedCurrencyError,
)
from app.domain.services.dsp_delivery_client import DspDeliveryClient
from app.domain.value_objects.delivery import DeliveryDateRange, ExternalLineKey
from app.infrastructure.dsp.adform_delivery_client import AdformDeliveryClient
from tests.fixtures.fake_adform import COLUMN_HEADERS, LOCATION_PATH, OPERATION_PATH, FakeAdform, report_row

RANGE = DeliveryDateRange(date(2026, 8, 3), date(2026, 8, 9))
CLIENT_ID = "synthetic-client-id"
CLIENT_SECRET = "synthetic-client-secret"


def _client(fake: FakeAdform, sleeps: list[float] | None = None, max_poll_attempts: int = 10,
            today: date = date(2026, 8, 10)) -> AdformDeliveryClient:
    recorded = sleeps if sleeps is not None else []
    return AdformDeliveryClient(
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET, http_client=fake.client(),
        max_poll_attempts=max_poll_attempts, sleep=recorded.append, today=lambda: today,
    )


def _fetch(fake: FakeAdform, **options):
    return list(_client(fake, **options).fetch_delivery(RANGE))


def test_it_is_a_dsp_delivery_client():
    assert isinstance(_client(FakeAdform()), DspDeliveryClient)


def test_the_token_is_requested_with_client_credentials_basic_auth_and_both_scopes():
    fake = FakeAdform(rows=[report_row()])

    _fetch(fake)

    token_request = fake.requests[0]
    assert (token_request.method, str(token_request.url)) == ("POST", "https://id.adform.com/sts/connect/token")
    expected_basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    assert token_request.headers["authorization"] == f"Basic {expected_basic}"
    body = token_request.content.decode()
    assert "grant_type=client_credentials" in body
    assert "buyer.stats" in body and "eapi" in body


def test_the_data_request_has_the_contracted_body_and_a_bearer_token():
    fake = FakeAdform(rows=[report_row()])

    _fetch(fake)

    data_request = next(r for r in fake.requests if r.url.path == "/v1/buyer/stats/data")
    assert str(data_request.url) == "https://api.adform.com/v1/buyer/stats/data"
    assert data_request.headers["authorization"] == "Bearer synthetic-access-token"
    assert json.loads(data_request.content) == {
        "dimensions": ["date", "campaignID", "lineItemID", "campaignCurrency"],
        "metrics": ["impressions", "clicks", "cost", "measurableImpressions", "viewImpressionsIAB"],
        "filter": {"date": {"from": "2026-08-03", "to": "2026-08-09"}},
        "paging": {"limit": 0},
    }


def test_a_run_makes_exactly_one_data_request():
    fake = FakeAdform(rows=[report_row()])

    _fetch(fake)

    assert fake.paths().count("POST api.adform.com/v1/buyer/stats/data") == 1


def test_running_twice_then_succeeded_polls_with_a_pause_and_reads_the_data_only_afterwards():
    fake = FakeAdform(rows=[report_row()], statuses=["running", "running", "succeeded"])
    sleeps: list[float] = []

    _fetch(fake, sleeps=sleeps)

    paths = fake.paths()
    assert paths.count(f"GET api.adform.com{OPERATION_PATH}") == 3
    assert paths.index(f"GET api.adform.com{LOCATION_PATH}") > max(
        i for i, p in enumerate(paths) if p == f"GET api.adform.com{OPERATION_PATH}")
    assert sleeps == [3.0, 3.0]


def test_an_unexpected_status_is_a_failure_and_the_data_is_never_read():
    fake = FakeAdform(rows=[report_row()], statuses=["running", "mystery"])

    with pytest.raises(DspReportFailedError):
        _fetch(fake)

    assert f"GET api.adform.com{LOCATION_PATH}" not in fake.paths()


def test_polling_gives_up_after_the_configured_attempts():
    fake = FakeAdform(statuses=["running"])

    with pytest.raises(DspReportTimeoutError):
        _fetch(fake, max_poll_attempts=4)

    assert fake.paths().count(f"GET api.adform.com{OPERATION_PATH}") == 4


def test_a_poll_interval_below_three_seconds_is_rejected():
    with pytest.raises(ValueError):
        AdformDeliveryClient(CLIENT_ID, CLIENT_SECRET, FakeAdform().client(), poll_interval_seconds=2.9)


@pytest.mark.parametrize("fake", [FakeAdform(token_status=401), FakeAdform(data_status=401)])
def test_a_401_is_an_authentication_failure(fake):
    with pytest.raises(DspAuthenticationError):
        _fetch(fake)


def test_a_request_timeout_means_the_dsp_is_unreachable():
    fake = FakeAdform(fail_with=httpx.ReadTimeout("timed out"))

    with pytest.raises(DspUnreachableError):
        _fetch(fake)


def test_a_connection_failure_means_the_dsp_is_unreachable():
    fake = FakeAdform(fail_with=httpx.ConnectError("refused"))

    with pytest.raises(DspUnreachableError):
        _fetch(fake)


def test_cost_keeps_six_decimals_exactly():
    rows = _fetch(FakeAdform(rows=[report_row(cost="12.345678")]))

    assert rows[0].media_cost == Decimal("12.345678")
    assert isinstance(rows[0].media_cost, Decimal)


def test_an_integer_cost_is_a_decimal_too():
    assert _fetch(FakeAdform(rows=[report_row(cost="7")]))[0].media_cost == Decimal(7)


def test_a_row_is_read_with_every_column_converted():
    row = _fetch(FakeAdform(rows=[report_row(impressions=1234, clicks=56, measurable=900, viewable=700)]))[0]

    assert row.key == ExternalLineKey("1001", "2001")
    assert row.delivery_date == date(2026, 8, 5)
    assert (row.impressions, row.clicks, row.measurable_impressions, row.viewable_impressions) == (1234, 56, 900, 700)
    assert (row.banner_size, row.screen, row.line_format) == (None, None, None)


def test_columns_are_read_by_header_name_not_by_position():
    shuffled = list(reversed(COLUMN_HEADERS))
    reversed_row = list(reversed(report_row(impressions=4321, line_item_id=77)))

    row = _fetch(FakeAdform(rows=[reversed_row], headers=shuffled))[0]

    assert (row.impressions, row.key) == (4321, ExternalLineKey("1001", "77"))


def test_a_missing_column_is_a_format_error_naming_it():
    headers = [h for h in COLUMN_HEADERS if h != "viewImpressionsIAB"]
    row = [cell for cell, header in zip(report_row(), COLUMN_HEADERS) if header != "viewImpressionsIAB"]

    with pytest.raises(DspResponseFormatError, match="viewImpressionsIAB"):
        _fetch(FakeAdform(rows=[row], headers=headers))


@pytest.mark.parametrize("line_item_id", [0, -1])
def test_a_row_without_an_attributed_line_item_and_currency_dash_has_no_key(line_item_id):
    row = _fetch(FakeAdform(rows=[report_row(line_item_id=line_item_id, currency="-")]))[0]

    assert row.key is None


def test_a_currency_other_than_eur_is_an_error_not_a_conversion():
    with pytest.raises(UnsupportedCurrencyError):
        _fetch(FakeAdform(rows=[report_row(currency="GBP")]))


def test_a_dash_currency_on_an_attributed_line_item_is_also_an_error():
    with pytest.raises(UnsupportedCurrencyError):
        _fetch(FakeAdform(rows=[report_row(line_item_id=2001, currency="-")]))


def test_an_empty_report_yields_no_rows():
    assert _fetch(FakeAdform(rows=[])) == []


def test_identifiers_are_found_when_they_appear_in_the_last_thirty_days():
    fake = FakeAdform(rows=[report_row(campaign_id=1001, line_item_id=2001)])

    found = _client(fake).resolve_identifiers("1001", "2001")

    assert found == ExternalLineKey("1001", "2001")
    data_request = next(r for r in fake.requests if r.url.path == "/v1/buyer/stats/data")
    assert json.loads(data_request.content)["filter"]["date"] == {"from": "2026-07-11", "to": "2026-08-09"}


def test_identifiers_absent_from_the_last_thirty_days_are_unknown():
    fake = FakeAdform(rows=[report_row(campaign_id=1001, line_item_id=2001)])

    assert _client(fake).resolve_identifiers("1001", "9999") is None


def test_an_unreachable_dsp_is_an_error_while_resolving_not_an_unknown_pair():
    fake = FakeAdform(fail_with=httpx.ConnectError("refused"))

    with pytest.raises(DspUnreachableError):
        _client(fake).resolve_identifiers("1001", "2001")
