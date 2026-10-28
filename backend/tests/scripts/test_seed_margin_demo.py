"""The demonstration data of the margin: three synthetic campaigns, idempotent, counts-only output, nothing real."""

import re
from datetime import date, datetime, UTC
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.infrastructure.persistence.models.campaign import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignPeriodRecord,
    CampaignRecord,
)
from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord, IngestionBatchRecord
from app.infrastructure.persistence.models.identity import RoleRecord, UserRecord
from app.infrastructure.persistence.models.margin import (
    AppliedRateRecord,
    PlatformRateSettingRecord,
    RebateBracketRecord,
    RebateScheduleRecord,
)
from app.infrastructure.persistence.models.masters import (
    AdvertiserRecord,
    AgencyRecord,
    CampaignTypeRecord,
    ChannelRecord,
    DSPRecord,
    FormatRecord,
    HoldingGroupRecord,
    SalesRepRecord,
    SectorRecord,
)
from app.infrastructure.persistence.models.purchase_order import PurchaseOrderRecord
from scripts.seed_margin_demo import (
    CLOSED_NAME,
    EXIT_FAILED,
    EXIT_INVALID_ARGUMENTS,
    EXIT_NOT_CONFIGURED,
    EXIT_OK,
    NO_PRICE_NAME,
    RUNNING_NAME,
    main,
)
from tests.fixtures.delivery_data import insert_campaign_line

TODAY = date(2026, 10, 28)  # the previous month is September; next month is November
NAMES = {CLOSED_NAME, RUNNING_NAME, NO_PRICE_NAME}

MASTER_MODELS = (
    HoldingGroupRecord, AgencyRecord, AdvertiserRecord, DSPRecord, ChannelRecord, FormatRecord, CampaignTypeRecord,
    SectorRecord, SalesRepRecord,
)
SEEDED_TABLES = (
    CampaignRecord, CampaignPeriodRecord, CampaignLineRecord, CampaignLinePeriodRecord, DailyDeliveryRecord,
    IngestionBatchRecord, PurchaseOrderRecord, RebateScheduleRecord, RebateBracketRecord, *MASTER_MODELS,
)


def _run(session, today: date = TODAY, **kwargs) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = main([], out=lines.append, session_factory=lambda: session, today=today, **kwargs)
    return code, lines


def _counts(session, tables=SEEDED_TABLES) -> dict[str, int]:
    return {table.__tablename__: session.scalar(select(func.count()).select_from(table)) for table in tables}


def _campaign(session, name: str) -> CampaignRecord:
    return session.scalars(select(CampaignRecord).where(CampaignRecord.name == name)).one()


def _line(session, name: str) -> CampaignLineRecord:
    return session.scalars(select(CampaignLineRecord).where(CampaignLineRecord.campaign_id == _campaign(session, name).id)).one()


def _flights(session, name: str) -> list[tuple[date, date]]:
    line = _line(session, name)
    rows = session.scalars(
        select(CampaignLinePeriodRecord).where(CampaignLinePeriodRecord.campaign_line_id == line.id)
        .order_by(CampaignLinePeriodRecord.flight_start)
    )
    return [(row.flight_start, row.flight_end) for row in rows]


# ---------------------------------------------------------------- what it creates

def test_it_creates_three_campaigns_with_neutral_names_and_one_line_each(rolled_back_session):
    code, _ = _run(rolled_back_session)

    assert code == EXIT_OK
    assert {c.name for c in rolled_back_session.scalars(select(CampaignRecord))} == NAMES
    assert NAMES == {"DEMO-MARGEN-CERRADO", "DEMO-MARGEN-CURSO", "DEMO-MARGEN-SIN-PRECIO"}
    for name in NAMES:
        assert rolled_back_session.scalar(
            select(func.count()).select_from(CampaignLineRecord).where(CampaignLineRecord.campaign_id == _campaign(rolled_back_session, name).id)
        ) == 1


def test_the_closed_campaign_fills_the_whole_previous_month(rolled_back_session):
    _run(rolled_back_session)

    assert _flights(rolled_back_session, CLOSED_NAME) == [(date(2026, 9, 1), date(2026, 9, 30))]
    campaign = _campaign(rolled_back_session, CLOSED_NAME)
    assert (campaign.start_date, campaign.end_date) == (date(2026, 9, 1), date(2026, 9, 30))


def test_the_running_campaigns_start_ten_days_ago_and_end_next_month(rolled_back_session):
    _run(rolled_back_session)

    for name in (RUNNING_NAME, NO_PRICE_NAME):
        campaign = _campaign(rolled_back_session, name)
        assert (campaign.start_date, campaign.end_date) == (date(2026, 10, 18), date(2026, 11, 30))
        assert _flights(rolled_back_session, name) == [
            (date(2026, 10, 18), date(2026, 10, 31)), (date(2026, 11, 1), date(2026, 11, 30)),
        ]


def test_the_third_campaign_has_a_sale_cpm_of_zero_and_a_positive_volume(rolled_back_session):
    _run(rolled_back_session)

    free = _line(rolled_back_session, NO_PRICE_NAME)
    priced = _line(rolled_back_session, RUNNING_NAME)
    assert free.sale_cpm == Decimal("0.00") and free.contracted_impressions > 0
    assert priced.sale_cpm > 0 and _line(rolled_back_session, CLOSED_NAME).sale_cpm > 0


def test_the_dates_follow_today_in_madrid(rolled_back_session):
    # 23:30 UTC on 27 October is 00:30 on 28 October in Madrid (winter time since the 25th).
    code, _ = _run(rolled_back_session, today=None, clock=lambda: datetime(2026, 10, 27, 23, 30, tzinfo=UTC))

    assert code == EXIT_OK
    assert _flights(rolled_back_session, CLOSED_NAME) == [(date(2026, 9, 1), date(2026, 9, 30))]
    assert _campaign(rolled_back_session, RUNNING_NAME).start_date == date(2026, 10, 18)


def test_it_follows_a_different_today(rolled_back_session):
    _run(rolled_back_session, today=date(2027, 1, 5))

    assert _flights(rolled_back_session, CLOSED_NAME) == [(date(2026, 12, 1), date(2026, 12, 31))]
    assert _campaign(rolled_back_session, RUNNING_NAME).start_date == date(2026, 12, 26)
    assert _campaign(rolled_back_session, RUNNING_NAME).end_date == date(2027, 2, 28)


def test_it_registers_through_the_registration_service_so_the_purchase_order_and_periods_exist(rolled_back_session):
    _run(rolled_back_session)

    assert rolled_back_session.scalar(select(func.count()).select_from(PurchaseOrderRecord)) == 3
    assert all(_campaign(rolled_back_session, name).purchase_order_id is not None for name in NAMES)
    assert all(_line(rolled_back_session, name).purchase_order_version_id is not None for name in NAMES)


# ---------------------------------------------------------------- deliveries and rebate

def test_each_line_has_daily_deliveries_up_to_yesterday_and_none_after(rolled_back_session):
    _run(rolled_back_session)

    for name in NAMES:
        line = _line(rolled_back_session, name)
        days = list(rolled_back_session.scalars(
            select(DailyDeliveryRecord.delivery_date).where(DailyDeliveryRecord.campaign_line_id == line.id)
            .order_by(DailyDeliveryRecord.delivery_date)
        ))
        campaign = _campaign(rolled_back_session, name)
        assert days[0] == campaign.start_date
        assert days[-1] == min(date(2026, 10, 27), campaign.end_date)
        assert len(days) == len(set(days)) == (days[-1] - days[0]).days + 1


def test_the_deliveries_are_invented_with_impressions_and_cost(rolled_back_session):
    _run(rolled_back_session)

    rows = rolled_back_session.scalars(select(DailyDeliveryRecord)).all()
    assert rows and all(row.impressions > 0 and row.media_cost > 0 for row in rows)
    assert all(isinstance(row.media_cost, Decimal) for row in rows)


def test_a_flat_example_schedule_exists_for_the_demonstration_group(rolled_back_session):
    _run(rolled_back_session)

    (schedule,) = rolled_back_session.scalars(select(RebateScheduleRecord)).all()
    brackets = rolled_back_session.scalars(select(RebateBracketRecord).where(RebateBracketRecord.rebate_schedule_id == schedule.id)).all()
    group = rolled_back_session.get(HoldingGroupRecord, schedule.holding_group_id)
    assert group.name.startswith("DEMO") and schedule.agency_id is None and schedule.valid_to is None
    assert len(brackets) == 1 and brackets[0].upper is None and brackets[0].rate > 0


# ---------------------------------------------------------------- idempotence

def test_a_second_run_changes_no_count(rolled_back_session):
    _run(rolled_back_session)
    first = _counts(rolled_back_session)

    code, lines = _run(rolled_back_session)

    assert code == EXIT_OK
    assert _counts(rolled_back_session) == first
    assert "campaigns created: 0" in lines and "campaigns existing: 3" in lines
    assert "rebate schedules created: 0" in lines and "masters created: 0" in lines


def test_the_first_run_says_what_it_created(rolled_back_session):
    _, lines = _run(rolled_back_session)

    assert "campaigns created: 3" in lines and "campaigns existing: 0" in lines
    assert "rebate schedules created: 1" in lines
    assert "masters created: 9" in lines


def test_a_second_run_leaves_the_same_deliveries_on_the_same_day(rolled_back_session):
    _run(rolled_back_session)
    before = rolled_back_session.execute(
        select(DailyDeliveryRecord.campaign_line_id, DailyDeliveryRecord.delivery_date, DailyDeliveryRecord.impressions,
               DailyDeliveryRecord.media_cost).order_by(DailyDeliveryRecord.campaign_line_id, DailyDeliveryRecord.delivery_date)
    ).all()

    _run(rolled_back_session)

    after = rolled_back_session.execute(
        select(DailyDeliveryRecord.campaign_line_id, DailyDeliveryRecord.delivery_date, DailyDeliveryRecord.impressions,
               DailyDeliveryRecord.media_cost).order_by(DailyDeliveryRecord.campaign_line_id, DailyDeliveryRecord.delivery_date)
    ).all()
    assert after == before


def test_a_later_day_adds_only_the_new_days(rolled_back_session):
    _run(rolled_back_session)
    first = rolled_back_session.scalar(select(func.count()).select_from(DailyDeliveryRecord))
    campaigns = _counts(rolled_back_session, (CampaignRecord, CampaignLineRecord, CampaignLinePeriodRecord))

    _run(rolled_back_session, today=date(2026, 10, 29))

    # The previous month is still September, so the campaigns exist; one more day for the two running lines.
    assert _counts(rolled_back_session, (CampaignRecord, CampaignLineRecord, CampaignLinePeriodRecord)) == campaigns
    assert rolled_back_session.scalar(select(func.count()).select_from(DailyDeliveryRecord)) == first + 2


# ---------------------------------------------------------------- nothing real

def test_it_touches_nothing_that_is_not_demonstration_data(rolled_back_session):
    real_line = insert_campaign_line(rolled_back_session, campaign_name="A real campaign")
    real_tables = (*SEEDED_TABLES, UserRecord, RoleRecord, AppliedRateRecord, PlatformRateSettingRecord)
    before = _counts(rolled_back_session, real_tables)

    _run(rolled_back_session)
    after = _counts(rolled_back_session, real_tables)

    assert after[UserRecord.__tablename__] == before[UserRecord.__tablename__]
    assert after[RoleRecord.__tablename__] == before[RoleRecord.__tablename__]
    assert after[AppliedRateRecord.__tablename__] == before[AppliedRateRecord.__tablename__] == 0
    assert after[PlatformRateSettingRecord.__tablename__] == before[PlatformRateSettingRecord.__tablename__]
    real = _campaign(rolled_back_session, "A real campaign")
    assert rolled_back_session.scalar(select(func.count()).select_from(DailyDeliveryRecord).where(
        DailyDeliveryRecord.campaign_line_id == real_line)) == 0
    assert real.status == "active"


def test_everything_it_creates_is_named_demo(rolled_back_session):
    before_names = {model: set(rolled_back_session.scalars(select(model.name))) for model in MASTER_MODELS}

    _run(rolled_back_session)

    for model, names in before_names.items():
        created = set(rolled_back_session.scalars(select(model.name))) - names
        assert created and all(name.startswith("DEMO") for name in created), model.__tablename__
    assert all(c.name.startswith("DEMO-MARGEN-") for c in rolled_back_session.scalars(select(CampaignRecord)))
    assert all(po.order_reference.startswith("DEMO-MARGEN-") for po in rolled_back_session.scalars(select(PurchaseOrderRecord)))
    batch = rolled_back_session.scalars(select(IngestionBatchRecord)).one()
    assert batch.source_file == "demo-margin"


def test_it_never_creates_a_user_a_role_or_a_frozen_rate(rolled_back_session):
    users = rolled_back_session.scalar(select(func.count()).select_from(UserRecord))

    _run(rolled_back_session)

    assert rolled_back_session.scalar(select(func.count()).select_from(UserRecord)) == users
    assert rolled_back_session.scalar(select(func.count()).select_from(AppliedRateRecord)) == 0


# ---------------------------------------------------------------- output and exit codes

def test_the_output_is_counts_only(rolled_back_session):
    _, lines = _run(rolled_back_session)

    assert lines
    assert all(re.fullmatch(r"[a-z ]+: \d+", line) for line in lines), lines
    text = "\n".join(lines)
    assert "DEMO" not in text and "@" not in text


def test_it_says_when_it_is_not_configured(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    lines: list[str] = []

    code = main([], out=lines.append, today=TODAY)

    assert code == EXIT_NOT_CONFIGURED
    assert lines == ["status: not configured"]


def test_it_refuses_arguments(rolled_back_session):
    lines: list[str] = []

    code = main(["--surprise"], out=lines.append, session_factory=lambda: rolled_back_session, today=TODAY)

    assert code == EXIT_INVALID_ARGUMENTS
    assert lines == ["status: invalid arguments"]
    assert rolled_back_session.scalar(select(func.count()).select_from(CampaignRecord)) == 0


def test_a_failure_prints_a_status_and_no_detail(rolled_back_session, monkeypatch):
    import scripts.seed_margin_demo as module

    def boom(*args, **kwargs):
        raise RuntimeError("secret detail of the failure")

    monkeypatch.setattr(module, "_register_missing", boom)
    lines: list[str] = []

    code = main([], out=lines.append, session_factory=lambda: rolled_back_session, today=TODAY)

    assert code == EXIT_FAILED
    assert lines == ["status: failed"]
