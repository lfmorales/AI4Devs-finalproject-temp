"""What the nightly command prints: states and counts, never a value from the data, the account or the DSP's errors."""

import re
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.domain.exceptions import DspUnreachableError
from app.domain.value_objects.delivery import DeliveryDateRange, DspDeliveryRow, ExternalLineKey
from scripts.run_ingestion import NIGHTLY_INGESTION_LOCK_KEY, main
from tests.fixtures.delivery_rows import dsp_row
from tests.fixtures.dsp_delivery_client import InMemoryDspDeliveryClient
from tests.scripts.test_run_ingestion import Scenario

D5 = date(2026, 8, 5)
SECRET_ID, SECRET_VALUE = "synthetic-adform-id-5150", "synthetic-adform-secret-6160"
KEY = ExternalLineKey("5551001", "5552001")
STRANGER = ExternalLineKey("5559001", "5559002")
NAME = "Synthetic Campaign Name 4242"

# Distinctive values that must never be echoed: identifiers, names, amounts, the account and the DSP's words.
VALUES = [
    "5551001", "5552001", "5559001", "5559002", NAME, "Synthetic Campaign Name", "7770011", "8880022", "9990033",
    "1234.567891", "ACME-42", "secret-token", SECRET_ID, SECRET_VALUE, "2026-08-05",
]
ALLOWED_LINE = re.compile(
    r"^(status: (succeeded|failed|not configured|another run is in progress)"
    r"|error: [A-Za-z]+Error"
    r"|(rows_read|ignored_rows|zero_unmatched_rows|new_exceptions|mapped_lines|skipped_lines|absences): \d+)$"
)


class FailsWithDetail(InMemoryDspDeliveryClient):
    def fetch_delivery(self, date_range: DeliveryDateRange) -> Iterator[DspDeliveryRow]:
        raise DspUnreachableError("Adform said: token secret-token for account ACME-42 expired at 7770011")


def _rows():
    return [
        dsp_row(D5, KEY, impressions=7770011, clicks=8880022, media_cost=Decimal("1234.567891")),
        dsp_row(D5, STRANGER, impressions=9990033, media_cost=Decimal("1234.567891")),
        dsp_row(D5, ExternalLineKey("5559003", "5559004"), impressions=0, media_cost=Decimal("0")),
    ]


def _scenario(session, engine, client_class=InMemoryDspDeliveryClient) -> Scenario:
    scenario = Scenario(session, engine, rows=_rows(), client_class=client_class)
    session.execute(text("UPDATE campaigns SET name = :name, display_name = :name"), {"name": NAME})
    session.execute(text("UPDATE dsp_mappings SET external_campaign_id = '5551001', external_line_item_id = '5552001'"
                         " WHERE external_campaign_id = '1001'"))
    session.commit()
    return scenario


def _assert_clean(output: list[str]) -> None:
    printed = "\n".join(output)
    assert output
    for value in VALUES:
        assert value not in printed, f"{value!r} appeared in the output"
    assert all(ALLOWED_LINE.match(line) for line in output), output


def test_a_successful_run_prints_only_states_and_counts(rolled_back_session, test_engine, monkeypatch):
    monkeypatch.setenv("ADFORM_CLIENT_ID", SECRET_ID)
    monkeypatch.setenv("ADFORM_CLIENT_SECRET", SECRET_VALUE)
    scenario = _scenario(rolled_back_session, test_engine)

    assert scenario.run() == 0

    _assert_clean(scenario.output)
    assert "rows_read: 3" in scenario.output and "zero_unmatched_rows: 1" in scenario.output
    assert "new_exceptions: 1" in scenario.output


def test_a_failure_prints_the_class_of_the_error_and_nothing_the_dsp_said(rolled_back_session, test_engine):
    scenario = _scenario(rolled_back_session, test_engine, client_class=FailsWithDetail)

    assert scenario.run() == 1

    _assert_clean(scenario.output)
    assert scenario.output == ["status: failed", "error: DspUnreachableError"]


def test_a_busy_lock_prints_only_its_state(rolled_back_session, test_engine):
    scenario = _scenario(rolled_back_session, test_engine)
    with test_engine.connect() as holder:
        holder.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": NIGHTLY_INGESTION_LOCK_KEY})
        try:
            assert scenario.run() == 2
        finally:
            holder.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": NIGHTLY_INGESTION_LOCK_KEY})

    _assert_clean(scenario.output)


def test_missing_configuration_prints_no_variable_name_or_value(rolled_back_session, test_engine, monkeypatch, capsys):
    monkeypatch.setenv("ADFORM_CLIENT_ID", SECRET_ID)
    monkeypatch.delenv("ADFORM_CLIENT_SECRET", raising=False)
    _scenario(rolled_back_session, test_engine)

    code = main(["--date", "2026-08-10"], engine=test_engine, session_factory=lambda: rolled_back_session)

    printed = capsys.readouterr()
    assert code == 3
    _assert_clean(printed.out.splitlines())
    assert printed.err == ""
