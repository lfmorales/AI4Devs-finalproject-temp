"""What the nightly command prints: states and counts, never a value from the data, the account or the DSP's errors."""

import re
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.domain.exceptions import DspUnreachableError
from app.domain.value_objects.delivery import DeliveryDateRange, DspDeliveryRow, ExternalLineKey
from scripts.run_ingestion import main
from tests.fixtures.delivery_rows import catalog_info, dsp_row
from tests.fixtures.dsp_delivery_client import InMemoryDspDeliveryClient
from tests.fixtures.fake_equativ import REPORT_ID, FakeEquativ, package_row
from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord
from tests.fixtures.delivery_data import insert_campaign_line, insert_mapping
from tests.scripts.test_run_ingestion import EquativScenario, Scenario, close_month, held_lock

D5 = date(2026, 8, 5)
SECRET_ID, SECRET_VALUE = "synthetic-adform-id-5150", "synthetic-adform-secret-6160"
KEY = ExternalLineKey("5551001", "5552001")
STRANGER = ExternalLineKey("5559001", "5559002")
NAME = "Synthetic Campaign Name 4242"
CATALOGUE_CAMPAIGN = "Synthetic Catalogue Campaign 8811"
CATALOGUE_LINE = "Synthetic Catalogue Line 9922"

# Distinctive values that must never be echoed: identifiers, names, amounts, the account and the DSP's words.
VALUES = [
    "5551001", "5552001", "5559001", "5559002", NAME, "Synthetic Campaign Name", "7770011", "8880022", "9990033",
    CATALOGUE_CAMPAIGN, CATALOGUE_LINE, "2026-07-01", "1234.567891", "ACME-42", "secret-token", SECRET_ID, SECRET_VALUE, "2026-08-05",
]
ALLOWED_LINE = re.compile(
    r"^(status: (succeeded|failed|not configured|another run is in progress)"
    r"|error: [A-Za-z]+Error"
    r"|(rows_read|ignored_rows|zero_unmatched_rows|new_exceptions|mapped_lines|skipped_lines|absences"
    r"|closed_month_days): \d+"
    r"|absences: skipped, (custom range|before 06:00 UTC))$"
)


class FailsWithDetail(InMemoryDspDeliveryClient):
    def fetch_delivery(self, date_range: DeliveryDateRange) -> Iterator[DspDeliveryRow]:
        raise DspUnreachableError("Adform said: token secret-token for account ACME-42 expired at 7770011")


def _rows():
    named = catalog_info(CATALOGUE_CAMPAIGN, CATALOGUE_LINE)
    return [
        dsp_row(D5, KEY, impressions=7770011, clicks=8880022, media_cost=Decimal("1234.567891"), catalog=named),
        dsp_row(D5, STRANGER, impressions=9990033, media_cost=Decimal("1234.567891"), catalog=named),
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
    with held_lock(test_engine, scenario.dsp_id):
        assert scenario.run() == 2

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


def test_the_catalogue_names_flow_through_the_run_and_stay_out_of_the_output(
        rolled_back_session, test_engine, monkeypatch):
    from sqlalchemy import func, select

    from app.infrastructure.persistence.models.dsp_catalog import DspCatalogLineRecord

    monkeypatch.setenv("ADFORM_CLIENT_ID", SECRET_ID)
    monkeypatch.setenv("ADFORM_CLIENT_SECRET", SECRET_VALUE)
    scenario = _scenario(rolled_back_session, test_engine)

    assert scenario.run() == 0

    # The names really reached the catalogue, so their absence from the output is not for lack of data.
    stored = rolled_back_session.scalars(select(DspCatalogLineRecord.line_item_name)).all()
    assert stored == [CATALOGUE_LINE, CATALOGUE_LINE]
    _assert_clean(scenario.output)


def test_a_custom_range_prints_only_states_and_counts(rolled_back_session, test_engine, monkeypatch):
    from datetime import UTC, datetime

    monkeypatch.setenv("ADFORM_CLIENT_ID", SECRET_ID)
    monkeypatch.setenv("ADFORM_CLIENT_SECRET", SECRET_VALUE)
    scenario = _scenario(rolled_back_session, test_engine)

    code = main(
        ["--from", "2026-08-03", "--to", "2026-08-09"], out=scenario.output.append, engine=test_engine,
        session_factory=lambda: rolled_back_session, client=scenario.client,
        now=lambda: datetime(2026, 8, 10, 12, 0, tzinfo=UTC),
    )

    assert code == 0
    _assert_clean(scenario.output)
    assert "absences: skipped, custom range" in scenario.output


def test_an_invalid_range_prints_only_its_state(rolled_back_session, test_engine, monkeypatch):
    monkeypatch.setenv("ADFORM_CLIENT_ID", SECRET_ID)
    monkeypatch.setenv("ADFORM_CLIENT_SECRET", SECRET_VALUE)
    scenario = _scenario(rolled_back_session, test_engine)

    code = main(["--from", "2026-08-03"], out=scenario.output.append, engine=test_engine,
                session_factory=lambda: rolled_back_session, client=scenario.client)

    assert code == 3
    _assert_clean(scenario.output)


# The report id, the package ids, the package name and the amounts of the synthetic Equativ: never printed.
EQUATIV_VALUES = [REPORT_ID, "900000001", "900000002", "900000009", "Synthetic Package One", "338.954", "271.1632", "61628"]


def _assert_no_equativ_value(output: list[str]) -> None:
    _assert_clean(output)
    printed = "\n".join(output)
    for value in EQUATIV_VALUES:
        assert value not in printed, f"{value!r} appeared in the output"


@pytest.mark.parametrize("hour", [5, 7], ids=["before-06-00-utc", "after-06-00-utc"])
def test_an_equativ_run_prints_only_states_and_counts(rolled_back_session: Session, test_engine: Engine, hour: int) -> None:
    equativ = EquativScenario(rolled_back_session, test_engine)

    assert equativ.run("--dsp", "Equativ", now=datetime(2026, 11, 24, hour, 0, tzinfo=UTC)) == 0

    _assert_no_equativ_value(equativ.output)


def test_a_failed_equativ_run_prints_the_class_of_the_error_and_not_the_report(
    rolled_back_session: Session, test_engine: Engine
) -> None:
    fake = FakeEquativ(rows=[package_row()], statuses=["PubSubPublishSuccessful", "ReportGenerationFailed"])
    equativ = EquativScenario(rolled_back_session, test_engine, fake=fake)

    assert equativ.run("--dsp", "Equativ", "--date", "2026-11-24") == 1

    _assert_no_equativ_value(equativ.output)
    assert equativ.output == ["status: failed", "error: DspReportFailedError"]



# --- closed_month_days: the days of the window in a closed month, counted and still ingested ----------------------

NOVEMBER_KEY = ExternalLineKey("5553001", "5553002")


def _november_scenario(session: Session, engine: Engine) -> tuple[Scenario, int]:
    """A line from November to December that delivered on 28 November and on 1 December."""
    scenario = Scenario(session, engine)
    line_id = insert_campaign_line(session, "November line", date(2026, 11, 1), date(2026, 12, 31), dsp_id=scenario.dsp_id)
    insert_mapping(session, line_id, scenario.dsp_id, NOVEMBER_KEY.external_campaign_id,
                   NOVEMBER_KEY.external_line_item_id, validated_at=datetime(2026, 11, 1, 9, 0))
    session.commit()
    return scenario, line_id


def _november_client(impressions: int) -> InMemoryDspDeliveryClient:
    return InMemoryDspDeliveryClient([
        dsp_row(date(2026, 11, 28), NOVEMBER_KEY, impressions=impressions, media_cost=Decimal("100.000000")),
        dsp_row(date(2026, 12, 1), NOVEMBER_KEY, impressions=impressions, media_cost=Decimal("100.000000")),
    ])


def _stored(session: Session, line_id: int) -> list[tuple[date, int, Decimal]]:
    return [
        (row.delivery_date, row.impressions, row.media_cost)
        for row in session.scalars(
            select(DailyDeliveryRecord).where(DailyDeliveryRecord.campaign_line_id == line_id)
            .order_by(DailyDeliveryRecord.delivery_date)
        )
    ]


def test_a_run_whose_window_falls_in_a_closed_november_counts_five_days_and_still_ingests_them(
    rolled_back_session: Session, test_engine: Engine
) -> None:
    scenario, line_id = _november_scenario(rolled_back_session, test_engine)
    close_month(rolled_back_session, 2026, 11)

    # 3 December: the window is 26 November to 2 December, five of its days in November.
    code = main(
        ["--date", "2026-12-03"], out=scenario.output.append, engine=scenario.engine,
        session_factory=lambda: scenario.session, client=_november_client(1_000),
    )

    assert code == 0
    _assert_clean(scenario.output)
    assert "closed_month_days: 5" in scenario.output
    assert _stored(rolled_back_session, line_id) == [
        (date(2026, 11, 28), 1_000, Decimal("100.000000")), (date(2026, 12, 1), 1_000, Decimal("100.000000")),
    ]


def test_with_november_open_the_same_window_counts_none(rolled_back_session: Session, test_engine: Engine) -> None:
    scenario, _ = _november_scenario(rolled_back_session, test_engine)
    close_month(rolled_back_session, 2026, 10)  # a closed month outside the window counts nothing

    code = main(
        ["--date", "2026-12-03"], out=scenario.output.append, engine=scenario.engine,
        session_factory=lambda: scenario.session, client=_november_client(1_000),
    )

    assert code == 0
    assert "closed_month_days: 0" in scenario.output


def test_a_closed_month_changes_nothing_the_run_stores(rolled_back_session: Session, test_engine: Engine) -> None:
    scenario, line_id = _november_scenario(rolled_back_session, test_engine)

    def run(impressions: int) -> list[tuple[date, int, Decimal]]:
        assert main(
            ["--date", "2026-12-03"], out=scenario.output.append, engine=scenario.engine,
            session_factory=lambda: scenario.session, client=_november_client(impressions),
        ) == 0
        return _stored(rolled_back_session, line_id)

    open_month = run(2_000)
    close_month(rolled_back_session, 2026, 11)
    restated = run(3_000)
    rows_after = rolled_back_session.scalar(select(func.count()).select_from(DailyDeliveryRecord))
    again_with_the_same_figures = run(3_000)

    assert [impressions for _, impressions, _ in open_month] == [2_000, 2_000]
    assert [impressions for _, impressions, _ in restated] == [3_000, 3_000]  # the closed day is replaced too
    assert again_with_the_same_figures == restated
    assert rolled_back_session.scalar(select(func.count()).select_from(DailyDeliveryRecord)) == rows_after


def test_a_failed_run_prints_no_count_of_closed_days(rolled_back_session: Session, test_engine: Engine) -> None:
    scenario = _scenario(rolled_back_session, test_engine, client_class=FailsWithDetail)
    close_month(rolled_back_session, 2026, 8)

    assert scenario.run() == 1

    assert scenario.output == ["status: failed", "error: DspUnreachableError"]
    assert not any(line.startswith("closed_month_days") for line in scenario.output)
