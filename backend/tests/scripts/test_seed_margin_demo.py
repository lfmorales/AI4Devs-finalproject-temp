"""The demonstration data of the margin: four synthetic campaigns, idempotent, counts-only output, nothing real."""

import re
from datetime import date, datetime, UTC
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.campaign import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignPeriodRecord,
    CampaignRecord,
)
from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord, IngestionBatchRecord
from app.infrastructure.persistence.models.dsp_mapping import DSPMappingRecord
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
    DEAL_NAME,
    EXIT_FAILED,
    EXIT_INVALID_ARGUMENTS,
    EXIT_NOT_CONFIGURED,
    EXIT_OK,
    NEGATIVE_NAME,
    DOOH_NAME,
    NO_PRICE_NAME,
    RUNNING_NAME,
    main,
)
from tests.fixtures.delivery_data import insert_campaign_line

TODAY = date(2026, 10, 28)  # the previous month is September; next month is November
NAMES = {CLOSED_NAME, RUNNING_NAME, NEGATIVE_NAME, NO_PRICE_NAME}

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

def test_it_creates_four_campaigns_with_neutral_names_and_one_line_each(rolled_back_session):
    code, _ = _run(rolled_back_session)

    assert code == EXIT_OK
    assert {c.name for c in rolled_back_session.scalars(select(CampaignRecord))} == NAMES
    assert NAMES == {"DEMO-MARGEN-CERRADO", "DEMO-MARGEN-CURSO", "DEMO-MARGEN-NEGATIVO", "DEMO-MARGEN-SIN-PRECIO"}
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

    for name in (RUNNING_NAME, NEGATIVE_NAME, NO_PRICE_NAME):
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

    assert rolled_back_session.scalar(select(func.count()).select_from(PurchaseOrderRecord)) == 4
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


def test_the_running_and_the_negative_campaigns_share_window_volume_and_price_but_not_cost(rolled_back_session):
    _run(rolled_back_session)

    running, negative = _line(rolled_back_session, RUNNING_NAME), _line(rolled_back_session, NEGATIVE_NAME)
    assert running.contracted_impressions == negative.contracted_impressions
    assert running.sale_cpm == negative.sale_cpm == Decimal("6.00")
    assert _flights(rolled_back_session, RUNNING_NAME) == _flights(rolled_back_session, NEGATIVE_NAME)

    def cost_per_thousand(line) -> set[Decimal]:
        rows = rolled_back_session.scalars(select(DailyDeliveryRecord).where(DailyDeliveryRecord.campaign_line_id == line.id))
        return {(row.media_cost * 1000 / row.impressions).quantize(Decimal("0.01")) for row in rows}

    assert cost_per_thousand(running) == {Decimal("1.60")}
    assert cost_per_thousand(negative) == {Decimal("9.00")}


def test_a_database_seeded_with_the_previous_cost_gets_the_new_cost_on_the_next_run(rolled_back_session):
    _run(rolled_back_session)
    line = _line(rolled_back_session, RUNNING_NAME)
    rolled_back_session.execute(
        DailyDeliveryRecord.__table__.update().where(DailyDeliveryRecord.campaign_line_id == line.id)
        .values(media_cost=DailyDeliveryRecord.impressions * Decimal("9.00") / 1000)
    )

    _run(rolled_back_session)

    rows = rolled_back_session.scalars(select(DailyDeliveryRecord).where(DailyDeliveryRecord.campaign_line_id == line.id)).all()
    assert rows and all((row.media_cost * 1000 / row.impressions).quantize(Decimal("0.01")) == Decimal("1.60") for row in rows)


# ---------------------------------------------------------------- idempotence

def test_a_second_run_changes_no_count(rolled_back_session):
    _run(rolled_back_session)
    first = _counts(rolled_back_session)

    code, lines = _run(rolled_back_session)

    assert code == EXIT_OK
    assert _counts(rolled_back_session) == first
    assert "campaigns created: 0" in lines and "campaigns existing: 4" in lines
    assert "rebate schedules created: 0" in lines and "masters created: 0" in lines


def test_the_first_run_says_what_it_created(rolled_back_session):
    _, lines = _run(rolled_back_session)

    assert "campaigns created: 4" in lines and "campaigns existing: 0" in lines
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

    # The previous month is still September, so the campaigns exist; one more day for the three running lines.
    assert _counts(rolled_back_session, (CampaignRecord, CampaignLineRecord, CampaignLinePeriodRecord)) == campaigns
    assert rolled_back_session.scalar(select(func.count()).select_from(DailyDeliveryRecord)) == first + 3


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


# ---------------------------------------------------------------- the DOOH campaign: OTS on the real channel

def _real_dooh_channel(session: Session) -> ChannelRecord:
    """The real DOOH channel, counted in OTS, as the masters file and the development seed create it."""
    channel = session.scalars(select(ChannelRecord).where(ChannelRecord.name == "DOOH")).first()
    if channel is None:
        channel = ChannelRecord(name="DOOH", delivery_metric="ots")
        session.add(channel)
        session.flush()
    return channel


def _deliveries(session: Session, name: str) -> list[DailyDeliveryRecord]:
    line = _line(session, name)
    return list(session.scalars(
        select(DailyDeliveryRecord).where(DailyDeliveryRecord.campaign_line_id == line.id)
        .order_by(DailyDeliveryRecord.delivery_date)
    ))


def test_it_adds_one_campaign_on_the_real_dooh_channel_when_that_channel_exists(rolled_back_session: Session) -> None:
    dooh = _real_dooh_channel(rolled_back_session)

    code, lines = _run(rolled_back_session)

    assert code == EXIT_OK
    assert DOOH_NAME == "DEMO-MARGEN-DOOH"
    assert {c.name for c in rolled_back_session.scalars(select(CampaignRecord))} == {*NAMES, DOOH_NAME}
    assert _line(rolled_back_session, DOOH_NAME).channel_id == dooh.id
    assert "campaigns created: 5" in lines


def test_the_demo_channel_campaigns_stay_in_impressions_with_no_ots(rolled_back_session: Session) -> None:
    _real_dooh_channel(rolled_back_session)

    _run(rolled_back_session)

    demo = rolled_back_session.scalars(select(ChannelRecord).where(ChannelRecord.name == "DEMO Channel")).one()
    assert demo.delivery_metric == "impressions"
    for name in NAMES:
        assert _line(rolled_back_session, name).channel_id == demo.id
        assert {row.ots for row in _deliveries(rolled_back_session, name)} == {Decimal(0)}


def test_the_dooh_days_carry_ots_with_decimals_and_fewer_impressions_than_ots(rolled_back_session: Session) -> None:
    _real_dooh_channel(rolled_back_session)

    _run(rolled_back_session)

    rows = _deliveries(rolled_back_session, DOOH_NAME)
    assert rows
    assert all(row.impressions > 0 and row.ots > row.impressions for row in rows)
    assert all(isinstance(row.ots, Decimal) for row in rows)
    assert any(row.ots != row.ots.to_integral_value() for row in rows), "some days carry OTS with decimals"
    assert all(row.ots == row.ots.quantize(Decimal("0.0001")) for row in rows)
    assert all(row.media_cost > 0 for row in rows)


def test_a_second_run_with_the_dooh_campaign_changes_no_count_and_says_five_exist(rolled_back_session: Session) -> None:
    _real_dooh_channel(rolled_back_session)
    _run(rolled_back_session)
    first = _counts(rolled_back_session)
    ots_before = [row.ots for row in _deliveries(rolled_back_session, DOOH_NAME)]

    code, lines = _run(rolled_back_session)

    assert code == EXIT_OK
    assert _counts(rolled_back_session) == first
    assert "campaigns created: 0" in lines and "campaigns existing: 5" in lines
    assert [row.ots for row in _deliveries(rolled_back_session, DOOH_NAME)] == ots_before


def test_a_later_day_adds_one_new_dooh_day_with_the_other_four_lines(rolled_back_session: Session) -> None:
    _real_dooh_channel(rolled_back_session)
    _run(rolled_back_session)
    first = rolled_back_session.scalar(select(func.count()).select_from(DailyDeliveryRecord)) or 0

    _run(rolled_back_session, today=date(2026, 10, 29))

    # The four running lines (the DOOH one included) gain one day.
    assert rolled_back_session.scalar(select(func.count()).select_from(DailyDeliveryRecord)) == first + 4


def test_without_a_dooh_channel_it_adds_no_dooh_campaign_and_creates_no_channel(rolled_back_session: Session) -> None:
    existing = rolled_back_session.scalars(select(ChannelRecord).where(ChannelRecord.name == "DOOH")).first()
    assert existing is None

    _run(rolled_back_session)

    assert {c.name for c in rolled_back_session.scalars(select(CampaignRecord))} == NAMES
    assert rolled_back_session.scalars(select(ChannelRecord).where(ChannelRecord.name == "DOOH")).first() is None


def test_the_dooh_campaign_registers_in_one_metric_and_keeps_its_name_and_order_demo(rolled_back_session: Session) -> None:
    _real_dooh_channel(rolled_back_session)

    _run(rolled_back_session)

    campaign = _campaign(rolled_back_session, DOOH_NAME)
    order = rolled_back_session.get(PurchaseOrderRecord, campaign.purchase_order_id)
    assert order is not None and order.order_reference.startswith("DEMO-MARGEN-")


# ---------------------------------------------------------------- the Deal campaign: a target line on Equativ
#
# Today is 2026-10-28: September (30 days) is the worked example and October is running. The flight of September has a
# target of 1,000,000 at 5.00 €, served 1,100,000, with 4,400.00 € reported and 5,500.00 € of buyer's spend; the flight of
# October has a target of 1,500,000 and delivers above it. No call reaches Equativ: the deliveries are written directly.

SEPTEMBER = (date(2026, 9, 1), date(2026, 9, 30))
OCTOBER_TO_YESTERDAY = (date(2026, 10, 1), date(2026, 10, 27))


def _equativ_and_deal(session: Session) -> tuple[int, int]:
    """The Equativ DSP and the Deal channel, as the masters file and the development seed create them."""
    equativ = session.scalars(select(DSPRecord).where(DSPRecord.name == "Equativ")).first()
    if equativ is None:
        equativ = DSPRecord(name="Equativ", is_active=True)
        session.add(equativ)
    deal = session.scalars(select(ChannelRecord).where(ChannelRecord.name == "Deal")).first()
    if deal is None:
        deal = ChannelRecord(name="Deal", delivery_metric="impressions")
        session.add(deal)
    session.flush()
    return equativ.id, deal.id


def _sum_between(session: Session, line_id: int, window: tuple[date, date], column: object) -> object:
    return session.scalar(
        select(func.sum(column)).where(
            DailyDeliveryRecord.campaign_line_id == line_id, DailyDeliveryRecord.delivery_date.between(*window)
        )
    )


def test_it_adds_a_deal_campaign_with_one_target_line_on_equativ(rolled_back_session: Session) -> None:
    equativ, deal = _equativ_and_deal(rolled_back_session)

    assert _run(rolled_back_session)[0] == EXIT_OK

    assert DEAL_NAME == "DEMO-MARGEN-DEAL"
    line = _line(rolled_back_session, DEAL_NAME)
    assert (line.dsp_id, line.channel_id, line.volume_commitment, line.sale_cpm) == (equativ, deal, "target", Decimal("5.00"))
    flights = rolled_back_session.scalars(
        select(CampaignLinePeriodRecord).where(CampaignLinePeriodRecord.campaign_line_id == line.id)
        .order_by(CampaignLinePeriodRecord.flight_start)
    ).all()
    assert [(f.flight_start, f.flight_end, f.contracted_impressions) for f in flights] == [
        (date(2026, 9, 1), date(2026, 9, 30), 1_000_000), (date(2026, 10, 1), date(2026, 10, 31), 1_500_000),
    ]


def test_the_deal_line_is_mapped_to_the_package_written_validated_by_the_user(rolled_back_session: Session) -> None:
    equativ, _ = _equativ_and_deal(rolled_back_session)

    _run(rolled_back_session)

    (mapping,) = rolled_back_session.scalars(
        select(DSPMappingRecord).where(DSPMappingRecord.campaign_line_id == _line(rolled_back_session, DEAL_NAME).id)
    ).all()
    assert (mapping.dsp_id, mapping.external_campaign_id, mapping.external_line_item_id) == (equativ, "900000001", "900000001")
    assert mapping.validated_at is not None


def test_september_holds_the_worked_example(rolled_back_session: Session) -> None:
    _equativ_and_deal(rolled_back_session)

    _run(rolled_back_session)

    line = _line(rolled_back_session, DEAL_NAME).id
    days = rolled_back_session.scalar(select(func.count()).select_from(DailyDeliveryRecord).where(
        DailyDeliveryRecord.campaign_line_id == line, DailyDeliveryRecord.delivery_date.between(*SEPTEMBER)))
    assert days == 30
    assert _sum_between(rolled_back_session, line, SEPTEMBER, DailyDeliveryRecord.impressions) == 1_100_000
    assert _sum_between(rolled_back_session, line, SEPTEMBER, DailyDeliveryRecord.reported_revenue) == Decimal("4400.00")
    assert _sum_between(rolled_back_session, line, SEPTEMBER, DailyDeliveryRecord.buyer_spend) == Decimal("5500.00")
    assert _sum_between(rolled_back_session, line, SEPTEMBER, DailyDeliveryRecord.media_cost) == 0
    data = DailyDeliveryRecord.third_party_data_cost + DailyDeliveryRecord.audience_data_cost
    assert _sum_between(rolled_back_session, line, SEPTEMBER, data) == 0


def test_october_delivers_above_its_target_up_to_yesterday_with_a_data_cost(rolled_back_session: Session) -> None:
    _equativ_and_deal(rolled_back_session)

    _run(rolled_back_session)

    line = _line(rolled_back_session, DEAL_NAME).id
    dates = list(rolled_back_session.scalars(select(DailyDeliveryRecord.delivery_date).where(
        DailyDeliveryRecord.campaign_line_id == line, DailyDeliveryRecord.delivery_date >= date(2026, 10, 1))))
    assert (min(dates), max(dates), len(dates)) == (date(2026, 10, 1), date(2026, 10, 27), 27)
    served = _sum_between(rolled_back_session, line, OCTOBER_TO_YESTERDAY, DailyDeliveryRecord.impressions)
    # 27 of 31 days of a target of 1,500,000 expect 1,306,451.6: delivering more than 110 % of it is well above target.
    assert Decimal(str(served)) * 31 > 1_500_000 * 27 * Decimal("1.1")
    data = DailyDeliveryRecord.third_party_data_cost + DailyDeliveryRecord.audience_data_cost
    assert _sum_between(rolled_back_session, line, OCTOBER_TO_YESTERDAY, data) == Decimal("0.25")


def test_a_succeeded_equativ_batch_covers_the_last_day_of_september(rolled_back_session: Session) -> None:
    equativ, _ = _equativ_and_deal(rolled_back_session)

    _run(rolled_back_session)

    (batch,) = rolled_back_session.scalars(select(IngestionBatchRecord).where(IngestionBatchRecord.dsp_id == equativ)).all()
    assert batch.status == "succeeded"
    assert batch.window_start is not None and batch.window_end is not None
    assert batch.window_start <= date(2026, 9, 30) <= batch.window_end
    assert batch.window_end == date(2026, 10, 27)
    assert (batch.source_file or "").startswith("demo-margin")


def test_a_second_run_with_the_deal_campaign_changes_no_count_and_keeps_its_deliveries(rolled_back_session: Session) -> None:
    _equativ_and_deal(rolled_back_session)
    _run(rolled_back_session)
    before = _counts(rolled_back_session, (*SEEDED_TABLES, DSPMappingRecord))
    line = _line(rolled_back_session, DEAL_NAME).id
    amounts_before = _sum_between(rolled_back_session, line, SEPTEMBER, DailyDeliveryRecord.reported_revenue)

    code, lines = _run(rolled_back_session)

    assert code == EXIT_OK
    assert _counts(rolled_back_session, (*SEEDED_TABLES, DSPMappingRecord)) == before
    assert _sum_between(rolled_back_session, line, SEPTEMBER, DailyDeliveryRecord.reported_revenue) == amounts_before
    assert "campaigns created: 0" in lines


def test_without_equativ_or_deal_it_adds_no_deal_campaign_and_creates_neither(rolled_back_session: Session) -> None:
    has_equativ = rolled_back_session.scalars(select(DSPRecord).where(DSPRecord.name == "Equativ")).first() is not None
    has_deal = rolled_back_session.scalars(select(ChannelRecord).where(ChannelRecord.name == "Deal")).first() is not None
    assert not (has_equativ and has_deal), "this test needs a database without the Equativ DSP or the Deal channel"

    _run(rolled_back_session)

    assert DEAL_NAME not in {c.name for c in rolled_back_session.scalars(select(CampaignRecord))}
    assert (rolled_back_session.scalars(select(DSPRecord).where(DSPRecord.name == "Equativ")).first() is not None) == has_equativ
    assert (rolled_back_session.scalars(select(ChannelRecord).where(ChannelRecord.name == "Deal")).first() is not None) == has_deal


def test_the_demo_dsp_has_loaded_every_day_from_the_first_of_january_of_the_previous_month_to_yesterday(
    rolled_back_session: Session,
) -> None:
    # A month of this year closes only once its DSP has loaded its last day (committed-billing-and-review): the E2E
    # campaigns, on the DEMO DSP, close the previous month and an earlier one of the same year.
    _run(rolled_back_session)
    demo_dsp = rolled_back_session.scalars(select(DSPRecord.id).where(DSPRecord.name == "DEMO DSP")).one()

    (batch,) = rolled_back_session.scalars(select(IngestionBatchRecord).where(IngestionBatchRecord.dsp_id == demo_dsp)).all()

    assert (batch.status, batch.window_start, batch.window_end) == ("succeeded", date(2026, 1, 1), date(2026, 10, 27))


def test_in_january_the_demo_dsp_has_loaded_from_the_first_of_january_of_last_year(rolled_back_session: Session) -> None:
    # On 15 January 2027 the previous month is December 2026, so its year starts on 1 January 2026.
    _run(rolled_back_session, today=date(2027, 1, 15))
    demo_dsp = rolled_back_session.scalars(select(DSPRecord.id).where(DSPRecord.name == "DEMO DSP")).one()

    (batch,) = rolled_back_session.scalars(select(IngestionBatchRecord).where(IngestionBatchRecord.dsp_id == demo_dsp)).all()

    assert (batch.window_start, batch.window_end) == (date(2026, 1, 1), date(2027, 1, 14))
