"""The demonstration data of the exception queue: synthetic, idempotent, counts-only output, nothing real."""

import re
import unicodedata
from datetime import date

import pytest
from sqlalchemy import func, select

from app.infrastructure.persistence.models.campaign import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignPeriodRecord,
    CampaignRecord,
)
from app.infrastructure.persistence.models.delivery import (
    DailyDeliveryRecord,
    IngestionBatchRecord,
    IngestionExceptionDeliveryRecord,
    IngestionExceptionRecord,
)
from app.infrastructure.persistence.models.dsp_catalog import DspCatalogLineRecord
from app.infrastructure.persistence.models.dsp_mapping import DSPMappingRecord
from app.infrastructure.persistence.models.identity import RoleRecord, UserRecord
from app.infrastructure.persistence.models.masters import DSPRecord
from scripts.seed_exceptions_demo import (
    ABSENCE_NAME,
    CAMPAIGN_NAME,
    CATALOG_LINES,
    EXIT_FAILED,
    EXIT_INVALID_ARGUMENTS,
    EXIT_NO_DEVELOPMENT_USER,
    EXIT_NOT_CONFIGURED,
    EXIT_OK,
    main,
)
from tests.fixtures.delivery_data import insert_ingestion_batch, insert_other_dsp, insert_user

TODAY = date(2026, 10, 28)  # the previous month is September
DEVELOPER = "developer@example.com"
SEEDED_TABLES = (
    CampaignRecord, CampaignPeriodRecord, CampaignLineRecord, CampaignLinePeriodRecord, DailyDeliveryRecord,
    IngestionBatchRecord, IngestionExceptionRecord, IngestionExceptionDeliveryRecord, DspCatalogLineRecord,
    DSPMappingRecord, DSPRecord,
)


@pytest.fixture
def session(rolled_back_session):
    insert_user(rolled_back_session, DEVELOPER)
    rolled_back_session.commit()
    return rolled_back_session


def _run(session, today: date = TODAY, **kwargs) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = main([], out=lines.append, session_factory=lambda: session, today=today, developer_email=DEVELOPER, **kwargs)
    return code, lines


def _counts(session, tables=SEEDED_TABLES) -> dict[str, int]:
    return {table.__tablename__: session.scalar(select(func.count()).select_from(table)) for table in tables}


def _line(session, name: str) -> CampaignLineRecord:
    campaign_id = session.scalars(select(CampaignRecord.id).where(CampaignRecord.name == name)).one()
    return session.scalars(select(CampaignLineRecord).where(CampaignLineRecord.campaign_id == campaign_id)).one()


def _exceptions(session, exception_type: str, status: str) -> list[IngestionExceptionRecord]:
    return list(session.scalars(
        select(IngestionExceptionRecord)
        .where(IngestionExceptionRecord.exception_type == exception_type, IngestionExceptionRecord.status == status)
        .order_by(IngestionExceptionRecord.id)
    ))


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


# ------------------------------------------------------------------ the campaigns

def test_the_campaign_for_linking_has_one_unmapped_line_that_started_more_than_seven_days_ago(session):
    assert _run(session)[0] == EXIT_OK

    line = _line(session, CAMPAIGN_NAME)

    assert (TODAY - line.start_date).days > 7
    assert session.scalar(select(func.count()).select_from(DSPMappingRecord).where(DSPMappingRecord.campaign_line_id == line.id)) == 0


def test_the_absence_campaign_has_a_mapped_and_validated_line_and_a_finished_flight_with_no_delivery(session):
    _run(session)

    line = _line(session, ABSENCE_NAME)
    mapping = session.scalars(select(DSPMappingRecord).where(DSPMappingRecord.campaign_line_id == line.id)).one()
    flights = list(session.scalars(select(CampaignLinePeriodRecord).where(CampaignLinePeriodRecord.campaign_line_id == line.id)))

    assert mapping.validated_at is not None
    assert len(flights) >= 1 and all(flight.flight_end < TODAY for flight in flights)
    assert session.scalar(select(func.count()).select_from(DailyDeliveryRecord).where(DailyDeliveryRecord.campaign_line_id == line.id)) == 0


def test_both_campaigns_run_on_the_demonstration_dsp(session):
    _run(session)

    dsp_name = session.scalars(
        select(DSPRecord.name).where(DSPRecord.id.in_([_line(session, CAMPAIGN_NAME).dsp_id, _line(session, ABSENCE_NAME).dsp_id]))
    ).all()

    assert set(dsp_name) == {"DEMO DSP"}


# ------------------------------------------------------------------ the catalogue

def test_it_creates_five_catalogue_lines_with_invented_names_and_two_with_accents(session):
    _run(session)

    names = [line.line_item_name for line in session.scalars(select(DspCatalogLineRecord).order_by(DspCatalogLineRecord.id))]

    assert sorted(_plain(name) for name in names) == [f"DEMO Catalogo Linea {n}" for n in range(1, 6)]
    assert sum(1 for name in names if _plain(name) != name) >= 2


def test_every_external_identifier_has_nine_digits_and_starts_with_99(session):
    _run(session)

    stored = session.scalars(select(DspCatalogLineRecord)).all()
    identifiers = [i for line in stored for i in (line.external_campaign_id, line.external_line_item_id)]
    identifiers += [i for line in CATALOG_LINES for i in (line.external_campaign_id, line.external_line_item_id)]

    assert identifiers and all(re.fullmatch(r"99\d{7}", identifier) for identifier in identifiers)


def test_no_pair_of_the_seed_can_match_a_real_adform_identifier_of_seven_or_eight_digits(session):
    _run(session)

    mapped = session.scalars(select(DSPMappingRecord)).all()
    exceptions = session.scalars(select(IngestionExceptionRecord).where(IngestionExceptionRecord.external_line_item_id.is_not(None))).all()
    identifiers = {
        i for row in (*mapped, *exceptions) for i in (row.external_campaign_id, row.external_line_item_id) if i is not None
    }

    assert identifiers
    assert not any(7 <= len(identifier) <= 8 for identifier in identifiers)


def test_the_pairs_of_the_open_and_resolved_exceptions_are_in_the_catalogue(session):
    _run(session)

    catalogue = {(l.external_campaign_id, l.external_line_item_id) for l in session.scalars(select(DspCatalogLineRecord))}
    unmatched = session.scalars(
        select(IngestionExceptionRecord).where(IngestionExceptionRecord.exception_type == "unmatched_delivery")
    ).all()

    assert len(unmatched) == 4
    assert all((e.external_campaign_id, e.external_line_item_id) in catalogue for e in unmatched)


def test_the_absence_line_pair_is_in_the_catalogue_as_a_mapped_line(session):
    _run(session)

    mapping = session.scalars(select(DSPMappingRecord).where(DSPMappingRecord.campaign_line_id == _line(session, ABSENCE_NAME).id)).one()

    assert (mapping.external_campaign_id, mapping.external_line_item_id) in {
        (l.external_campaign_id, l.external_line_item_id) for l in session.scalars(select(DspCatalogLineRecord))
    }


# ------------------------------------------------------------------ the exceptions

def test_it_creates_three_open_unmatched_exceptions_with_delivery_retained_by_day(session):
    _run(session)

    open_unmatched = _exceptions(session, "unmatched_delivery", "open")

    assert len(open_unmatched) == 3
    for exception in open_unmatched:
        rows = session.scalars(
            select(IngestionExceptionDeliveryRecord).where(IngestionExceptionDeliveryRecord.exception_id == exception.id)
        ).all()
        assert len(rows) >= 3
        assert len({row.delivery_date for row in rows}) == len(rows)
        assert all(row.delivery_date < TODAY and row.impressions > 0 for row in rows)
        assert exception.first_date == min(row.delivery_date for row in rows)
        assert exception.last_date == max(row.delivery_date for row in rows)


def test_it_creates_one_resolved_exception_with_a_note_and_the_developer_as_resolver(session):
    _run(session)

    resolved = _exceptions(session, "unmatched_delivery", "resolved")
    developer = session.scalars(select(UserRecord.id).where(UserRecord.email == DEVELOPER)).one()

    assert len(resolved) == 1
    assert resolved[0].note and resolved[0].resolved_at is not None and resolved[0].resolved_by == developer


def test_it_creates_one_open_missing_delivery_on_the_absence_line(session):
    _run(session)

    missing = _exceptions(session, "missing_delivery", "open")

    assert len(missing) == 1
    assert missing[0].campaign_line_id == _line(session, ABSENCE_NAME).id
    assert missing[0].campaign_period_id is not None


# ------------------------------------------------------------------ idempotence

def test_a_second_run_changes_no_count(session):
    _run(session)
    after_first = _counts(session)

    code, _ = _run(session)

    assert code == EXIT_OK
    assert _counts(session) == after_first


def test_a_second_run_leaves_the_resolved_exception_resolved_and_the_open_ones_open(session):
    _run(session)
    before = [(e.id, e.status, e.note) for e in session.scalars(select(IngestionExceptionRecord).order_by(IngestionExceptionRecord.id))]

    _run(session)

    assert [(e.id, e.status, e.note) for e in session.scalars(select(IngestionExceptionRecord).order_by(IngestionExceptionRecord.id))] == before


def test_the_first_run_says_what_it_created_and_the_second_says_it_created_nothing(session):
    _, first = _run(session)
    _, second = _run(session)

    assert "campaigns created: 2" in first
    assert "campaigns created: 0" in second
    assert "exceptions created: 0" in second


# ------------------------------------------------------------------ nothing real

def test_it_touches_no_delivery_or_exception_of_another_dsp(session):
    other_dsp = insert_other_dsp(session, "Real looking DSP")
    batch = insert_ingestion_batch(session)
    session.add(IngestionExceptionRecord(
        exception_type="unmatched_delivery", status="open", ingestion_batch_id=batch, dsp_id=other_dsp,
        external_campaign_id="1234567", external_line_item_id="7654321", first_date=date(2026, 10, 20), last_date=date(2026, 10, 20),
    ))
    session.commit()
    before = session.scalar(select(func.count()).select_from(IngestionExceptionRecord).where(IngestionExceptionRecord.dsp_id == other_dsp))

    _run(session)

    assert before == 1
    assert session.scalar(select(func.count()).select_from(IngestionExceptionRecord).where(IngestionExceptionRecord.dsp_id == other_dsp)) == 1


def test_everything_it_creates_is_named_demo(session):
    _run(session)

    names = list(session.scalars(select(CampaignRecord.name)))
    names += [l.line_item_name for l in session.scalars(select(DspCatalogLineRecord))]
    names += [l.campaign_name for l in session.scalars(select(DspCatalogLineRecord))]

    assert names and all(name.startswith("DEMO") for name in names)


def test_it_never_creates_a_user_or_a_role(session):
    before = _counts(session, (UserRecord, RoleRecord))

    _run(session)

    assert _counts(session, (UserRecord, RoleRecord)) == before


# ------------------------------------------------------------------ the command

def test_the_output_is_counts_only(session):
    _, lines = _run(session)

    assert lines and all(re.fullmatch(r"[a-z ]+: \d+", line) for line in lines)
    text = "\n".join(lines)
    assert "DEMO" not in text and DEVELOPER not in text
    assert not any(re.search(r"99\d{7}", line) for line in lines)


def test_without_a_development_user_it_says_to_run_the_dev_seed_first(rolled_back_session):
    lines: list[str] = []

    code = main([], out=lines.append, session_factory=lambda: rolled_back_session, today=TODAY, developer_email=DEVELOPER)

    assert code == EXIT_NO_DEVELOPMENT_USER
    assert any("seed_dev_data" in line for line in lines)
    assert EXIT_NO_DEVELOPMENT_USER not in (EXIT_OK, EXIT_FAILED, EXIT_INVALID_ARGUMENTS, EXIT_NOT_CONFIGURED)
    assert rolled_back_session.scalar(select(func.count()).select_from(CampaignRecord)) == 0


def test_it_says_when_it_is_not_configured(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    lines: list[str] = []

    code = main([], out=lines.append)

    assert (code, lines) == (EXIT_NOT_CONFIGURED, ["status: not configured"])


def test_it_refuses_arguments(session):
    lines: list[str] = []

    code = main(["--whatever"], out=lines.append, session_factory=lambda: session, today=TODAY, developer_email=DEVELOPER)

    assert (code, lines) == (EXIT_INVALID_ARGUMENTS, ["status: invalid arguments"])


def test_a_failure_prints_a_status_and_no_detail(session, monkeypatch):
    import scripts.seed_exceptions_demo as module

    def boom(*args, **kwargs):
        raise RuntimeError("secret detail of the failure")

    monkeypatch.setattr(module, "seed", boom)
    lines: list[str] = []

    code = main([], out=lines.append, session_factory=lambda: session, today=TODAY, developer_email=DEVELOPER)

    assert (code, lines) == (EXIT_FAILED, ["status: failed"])
