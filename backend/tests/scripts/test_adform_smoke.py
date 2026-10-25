"""The smoke script shows counts and column types of a real Adform report, and never a value from it."""

import json
import subprocess
import sys
from datetime import date, timedelta

import httpx
import pytest

from scripts import adform_smoke
from tests.conftest import BACKEND_ROOT
from tests.fixtures.fake_adform import LOCATION_PATH, TOKEN_VALUE, FakeAdform, report_row

SECRET = "synthetic-smoke-secret"
ENVIRONMENT = {"ADFORM_CLIENT_ID": "synthetic-smoke-id", "ADFORM_CLIENT_SECRET": SECRET}
YESTERDAY = date.today() - timedelta(days=1)

# Distinctive synthetic values: any of them in the output would be a leak.
SYNTHETIC_VALUES = ["777001", "777002", "888001", "888002", "31415926", "27182", "27182.818281", "2031-02-03",
                    "16180339", "14142"]


def _report_rows():
    return [
        report_row("2031-02-03T00:00:00", 777001, 888001, "EUR", 31415926, 27182, "27182.818281", 16180339, 14142),
        report_row("2031-02-04T00:00:00", 777001, 888001, "EUR", 31415926, 27182, "7", 16180339, 14142),
        report_row("2031-02-03T00:00:00", 777002, 888002, "EUR", 31415926, 27182, "27182.818281", 16180339, 14142),
        report_row("2031-02-03T00:00:00", 777001, 0, "-", 31415926, 27182, "27182.818281", 16180339, 14142),
        report_row("2031-02-03T00:00:00", 777002, 888003, "GBP", 31415926, 27182, "27182.818281", 16180339, 14142),
    ]


def _run(fake: FakeAdform, environment: dict[str, str] | None = None) -> tuple[int, str]:
    lines: list[str] = []
    code = adform_smoke.main(
        environ=ENVIRONMENT if environment is None else environment,
        http_client=fake.client(),
        out=lines.append,
        sleep=lambda _: None,
    )
    return code, "\n".join(lines)


def test_it_prints_the_final_status_and_the_counts():
    code, output = _run(FakeAdform(rows=_report_rows(), statuses=["running", "succeeded"]))

    assert code == 0
    assert "operation status: succeeded" in output
    assert "rows: 5" in output
    assert "rows without an attributed line item (ignored): 1" in output
    assert "rows in EUR: 3" in output
    assert "distinct (campaign, line item) pairs among attributed rows: 3" in output


def test_it_prints_the_type_of_every_column_and_nothing_else_about_it():
    _, output = _run(FakeAdform(rows=_report_rows()))

    assert "date: string" in output
    assert "campaignID: integer" in output
    assert "campaignCurrency: string" in output
    assert "impressions: integer" in output
    assert "cost: decimal | integer" in output


def test_no_value_from_the_report_appears_in_the_output():
    _, output = _run(FakeAdform(rows=_report_rows()))

    for value in SYNTHETIC_VALUES:
        assert value not in output


def test_neither_the_secret_nor_the_token_appears_in_the_output():
    _, output = _run(FakeAdform(rows=_report_rows()))

    assert SECRET not in output and TOKEN_VALUE not in output


def test_it_makes_one_data_request_for_d_minus_1_only():
    fake = FakeAdform(rows=_report_rows(), statuses=["running", "running", "succeeded"])

    _run(fake)

    data_requests = [r for r in fake.requests if r.method == "POST" and r.url.path == "/v1/buyer/stats/data"]
    assert len(data_requests) == 1
    window = json.loads(data_requests[0].content)["filter"]["date"]
    assert window == {"from": YESTERDAY.isoformat(), "to": YESTERDAY.isoformat()}


def test_an_unexpected_final_status_is_shown_and_the_report_is_never_read():
    fake = FakeAdform(rows=_report_rows(), statuses=["running", "mystery"])

    code, output = _run(fake)

    assert code == 1
    assert "operation status: mystery" in output
    assert f"GET api.adform.com{LOCATION_PATH}" not in fake.paths()
    for value in SYNTHETIC_VALUES:
        assert value not in output


def test_missing_credentials_name_the_variables_and_make_no_request():
    fake = FakeAdform(rows=_report_rows())

    code, output = _run(fake, environment={})

    assert code == 2
    assert "ADFORM_CLIENT_ID" in output and "ADFORM_CLIENT_SECRET" in output
    assert fake.requests == []


def test_an_unreachable_adform_prints_the_error_kind_and_no_detail():
    code, output = _run(FakeAdform(fail_with=httpx.ConnectError("refused to connect to adform.internal")))

    assert code == 1
    assert "DspUnreachableError" in output
    assert "adform.internal" not in output


def test_an_empty_report_prints_zero_counts():
    code, output = _run(FakeAdform(rows=[]))

    assert code == 0
    assert "rows: 0" in output


def test_it_writes_nothing_to_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    _run(FakeAdform(rows=_report_rows()))

    assert list(tmp_path.iterdir()) == []


def test_it_does_not_load_the_database_layer():
    probe = "import scripts.adform_smoke, sys; sys.exit(int(any(m.split('.')[0] == 'sqlalchemy' for m in sys.modules)))"

    # A failed import also exits non-zero but writes a traceback to stderr, so both must be clean.
    result = subprocess.run(
        [sys.executable, "-c", probe], cwd=BACKEND_ROOT, env={"PYTHONPATH": str(BACKEND_ROOT)},
        capture_output=True, text=True,
    )

    assert (result.returncode, result.stderr) == (0, "")


def _zero_impression_rows():
    zero = {"impressions": 0}
    return [
        report_row("2031-02-03T00:00:00", 777001, 888001, "EUR", **zero),           # attributed, zero
        report_row("2031-02-04T00:00:00", 777001, 888001, "EUR", **zero),           # attributed, zero
        report_row("2031-02-03T00:00:00", 777002, 888002, "EUR", impressions=31415926),  # attributed, not zero
        report_row("2031-02-03T00:00:00", 777001, 0, "-", **zero),                  # no line item, zero
        report_row("2031-02-03T00:00:00", 777002, 888003, "GBP", **zero),           # not EUR, zero
        report_row("2031-02-03T00:00:00", 777002, 0, "-", impressions=31415926),    # no line item, not zero
    ]


def test_it_counts_zero_impression_rows_with_and_without_an_attributed_line():
    _, output = _run(FakeAdform(rows=_zero_impression_rows()))

    assert "rows with zero impressions, attributed (line item > 0, EUR): 2" in output
    assert "rows with zero impressions, not attributed: 2" in output


def test_the_zero_impression_counts_show_no_value_from_the_report():
    _, output = _run(FakeAdform(rows=_zero_impression_rows()))

    for value in SYNTHETIC_VALUES:
        assert value not in output


def test_a_report_without_zero_impressions_counts_zero_in_both():
    _, output = _run(FakeAdform(rows=_report_rows()))

    assert "rows with zero impressions, attributed (line item > 0, EUR): 0" in output
    assert "rows with zero impressions, not attributed: 0" in output


CATALOGUE_NAMES = ["Synthetic Spring Sale 7733", "Synthetic Banner Line 8844", "2031-06-01", "2031-09-30"]


def _named_rows():
    return [
        report_row("2031-02-03T00:00:00", 777001, 888001, "EUR", 31415926, 27182, "27182.818281", 16180339, 14142,
                   campaign_name=CATALOGUE_NAMES[0], line_item_name=CATALOGUE_NAMES[1],
                   line_start="2031-06-01T00:00:00", line_end="2031-09-30T23:59:59"),
    ]


def test_it_shows_the_type_of_the_name_and_date_columns_and_none_of_their_values():
    code, output = _run(FakeAdform(rows=_named_rows()))

    assert code == 0
    for column in ("campaign", "lineItem", "lineItemStartDate", "lineItemEndDate"):
        assert f"{column}: string" in output
    for value in CATALOGUE_NAMES:
        assert value not in output


def test_it_asks_for_the_eight_dimensions_in_its_single_request():
    fake = FakeAdform(rows=_named_rows())

    _run(fake)

    data_requests = [r for r in fake.requests if r.url.path == "/v1/buyer/stats/data" and r.method == "POST"]
    assert len(data_requests) == 1
    assert len(json.loads(data_requests[0].content)["dimensions"]) == 8
