"""One domain function prices flights for the closing and for the reads: rebate, platform rate and margin."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from app.domain.services.priced_flights import price_flights
from app.domain.value_objects.margin import FlightStatus
from app.domain.value_objects.platform_rate import PlatformRateLevel
from app.domain.value_objects.priced_flight import FlightFacts, PlatformRates
from app.domain.value_objects.rebate import Bracket, CounterKey, LadderStep, RebateSchedule
from app.domain.value_objects.volume_commitment import VolumeCommitment
from tests.fixtures.flight_inputs import flight_facts

GROUP = 10
AGENCY = 20
SYSTEM_RATE = Decimal("1.00")
FLAT_25 = (Bracket(Decimal(0), None, Decimal("0.25")),)
TWO_BRACKETS = (
    Bracket(Decimal(0), Decimal(100_000), Decimal("0.15")),
    Bracket(Decimal(100_000), None, Decimal("0.20")),
)


def schedule(brackets: tuple[Bracket, ...] = FLAT_25) -> RebateSchedule:
    return RebateSchedule(1, GROUP, None, "Directo", "national", date(2026, 1, 1), None, brackets)


def facts(
    flight_id: int = 1,
    flight_start: date = date(2026, 8, 1),
    flight_end: date = date(2026, 8, 31),
    contracted_impressions: int = 726_202,
    sale_cpm: str = "5.00",
    delivered_impressions: int = 700_000,
    media_cost: str = "1200.00",
    line_id: int = 100,
    agency_id: int = AGENCY,
    campaign_type_id: int = 7,
) -> FlightFacts:
    return flight_facts(
        flight_id=flight_id, campaign_line_id=line_id, campaign_id=1, flight_start=flight_start, flight_end=flight_end,
        group_id=GROUP, agency_id=agency_id, campaign_type_id=campaign_type_id, channel="Directo", channel_id=3,
        scope="national", contracted_impressions=contracted_impressions, sale_cpm=Decimal(sale_cpm),
        delivered_impressions=delivered_impressions, media_cost=Decimal(media_cost),
    )


AS_OF = date(2026, 9, 5)


def test_a_closed_flight_is_priced_end_to_end_with_the_specs_example():
    (priced,) = price_flights([schedule()], PlatformRates(system=SYSTEM_RATE), [facts()], AS_OF)

    assert priced.margin.status is FlightStatus.CLOSED
    assert priced.margin.revenue == Decimal("3631.01")
    assert priced.margin.media_cost == Decimal("1200.00")
    assert priced.margin.rebate == Decimal("907.75")  # 907.7525 exact
    assert priced.margin.platform_cost == Decimal("700.00")
    assert priced.margin.margin == Decimal("823.26")
    assert priced.rebate.rebate == Decimal("907.7525")
    assert priced.rebate.step is LadderStep.GROUP_CHANNEL_SCOPE
    assert priced.platform.rate == Decimal("1.00")
    assert priced.platform.level is PlatformRateLevel.SYSTEM


def test_the_counter_is_fed_with_the_rounded_revenue_of_the_flight():
    (priced,) = price_flights([schedule()], PlatformRates(system=SYSTEM_RATE), [facts()], AS_OF)

    assert priced.rebate.position_after == Decimal("3631.01")


def test_platform_rate_resolves_line_then_agency_then_campaign_type_then_system():
    rates = PlatformRates(
        system=Decimal("1.00"),
        by_campaign_type={7: Decimal("1.50")},
        by_agency={AGENCY: Decimal("1.20")},
        by_line={100: Decimal("0.80")},
    )

    by_line = price_flights([schedule()], rates, [facts(line_id=100)], AS_OF)[0].platform
    by_agency = price_flights([schedule()], rates, [facts(line_id=101)], AS_OF)[0].platform
    by_type = price_flights([schedule()], rates, [facts(line_id=101, agency_id=AGENCY + 1)], AS_OF)[0].platform
    by_system = price_flights([schedule()], rates, [facts(line_id=101, agency_id=AGENCY + 1, campaign_type_id=8)], AS_OF)[0].platform

    assert [(p.rate, p.level) for p in (by_line, by_agency, by_type, by_system)] == [
        (Decimal("0.80"), PlatformRateLevel.LINE),
        (Decimal("1.20"), PlatformRateLevel.AGENCY),
        (Decimal("1.50"), PlatformRateLevel.CAMPAIGN_TYPE),
        (Decimal("1.00"), PlatformRateLevel.SYSTEM),
    ]


def test_the_platform_cost_uses_the_resolved_rate():
    rates = PlatformRates(system=Decimal("1.00"), by_line={100: Decimal("2.00")})

    (priced,) = price_flights([schedule()], rates, [facts()], AS_OF)

    assert priced.margin.platform_cost == Decimal("1400.00")


def test_flights_of_a_counter_are_applied_in_order_whatever_the_input_order():
    first = facts(flight_id=1, flight_start=date(2026, 7, 1), flight_end=date(2026, 7, 31),
                  contracted_impressions=18_000_000, sale_cpm="5.00")   # 90,000 EUR
    second = facts(flight_id=2, contracted_impressions=6_000_000, sale_cpm="5.00")  # 30,000 EUR
    schedules = [schedule(TWO_BRACKETS)]

    forward = price_flights(schedules, PlatformRates(system=SYSTEM_RATE), [first, second], AS_OF)
    backward = price_flights(schedules, PlatformRates(system=SYSTEM_RATE), [second, first], AS_OF)

    assert forward == backward
    assert forward[1].rebate.position_before == Decimal(90_000)
    assert forward[1].rebate.rebate == Decimal(5_500)


def test_opening_positions_start_the_counter_where_the_frozen_rows_left_it():
    key = CounterKey(GROUP, None, "Directo", 2026)
    flight = facts(contracted_impressions=6_000_000, sale_cpm="5.00")

    (priced,) = price_flights(
        [schedule(TWO_BRACKETS)], PlatformRates(system=SYSTEM_RATE), [flight], AS_OF, opening_positions={key: Decimal(90_000)}
    )

    assert priced.rebate.position_before == Decimal(90_000)
    assert priced.rebate.rebate == Decimal(5_500)


def test_a_running_flight_is_pro_rated_by_the_margin_and_reads_the_full_rebate():
    running = facts(
        flight_start=date(2026, 9, 1), flight_end=date(2026, 9, 30), contracted_impressions=6_000_000,
        sale_cpm="5.00", delivered_impressions=90_000, media_cost="150.00",
    )

    (priced,) = price_flights([schedule()], PlatformRates(system=SYSTEM_RATE), [running], date(2026, 9, 10))

    assert priced.margin.status is FlightStatus.RUNNING
    assert priced.margin.provisional is True
    assert priced.rebate.rebate == Decimal(7_500)          # 25 % of the full 30,000
    assert priced.margin.revenue == Decimal("10000.00")    # 30,000 x 10 / 30
    assert priced.margin.rebate == Decimal("2500.00")      # 7,500 x 10 / 30
    assert priced.rebate.position_after == priced.rebate.position_before


def test_a_flight_that_has_not_started_is_not_priced():
    future = facts(flight_start=date(2026, 10, 1), flight_end=date(2026, 10, 31))

    assert price_flights([schedule()], PlatformRates(system=SYSTEM_RATE), [future], AS_OF) == ()


def test_a_flight_with_no_schedule_is_an_explicit_zero_and_still_has_a_margin():
    (priced,) = price_flights([], PlatformRates(system=SYSTEM_RATE), [facts()], AS_OF)

    assert priced.rebate.step is LadderStep.EXPLICIT_ZERO
    assert priced.margin.rebate == Decimal("0.00")
    assert priced.margin.margin == Decimal("3631.01") - Decimal("1200.00") - Decimal("700.00")


# --- A target flight is priced on its served gross and accrues it on its channel's counter (finance/rebate-accrual) ---

FLAT_10 = (Bracket(Decimal(0), None, Decimal("0.10")),)
TEN_THEN_FIFTEEN = (
    Bracket(Decimal(0), Decimal(100_000), Decimal("0.10")),
    Bracket(Decimal(100_000), None, Decimal("0.15")),
)
DEAL_COUNTER = CounterKey(GROUP, None, "Deal", 2026)
AFTER_NOVEMBER = date(2026, 12, 1)


def deal_schedule(brackets: tuple[Bracket, ...] = FLAT_10) -> RebateSchedule:
    return RebateSchedule(2, GROUP, None, "Deal", "national", date(2026, 1, 1), None, brackets)


def target_facts(
    flight_id: int = 1,
    flight_start: date = date(2026, 11, 1),
    flight_end: date = date(2026, 11, 30),
    contracted_impressions: int = 1_000_000,
    delivered_impressions: int = 1_100_000,
    reported_revenue: str = "4400.00",
    buyer_spend: str = "5500.00",
) -> FlightFacts:
    """A target Deal line on Equativ at 5.00 €: no media cost, earning what Equativ reports."""
    return flight_facts(
        flight_id=flight_id, campaign_line_id=200, campaign_id=2, flight_start=flight_start, flight_end=flight_end,
        group_id=GROUP, agency_id=AGENCY, campaign_type_id=7, channel="Deal", channel_id=4, scope="national",
        contracted_impressions=contracted_impressions, sale_cpm=Decimal("5.00"),
        delivered_impressions=delivered_impressions, media_cost=Decimal(0),
        volume_commitment=VolumeCommitment.TARGET, reported_revenue=Decimal(reported_revenue),
        buyer_spend=Decimal(buyer_spend),
    )


def test_the_worked_example_is_priced_on_its_gross_and_advances_the_deal_counter_by_it() -> None:
    (priced,) = price_flights(
        [deal_schedule()], PlatformRates(system=SYSTEM_RATE), [target_facts()], AFTER_NOVEMBER,
        opening_positions={DEAL_COUNTER: Decimal(20_000)},
    )

    assert priced.rebate.counter == DEAL_COUNTER
    assert priced.rebate.rebate == Decimal("550.00")  # 10 % of the gross 5,500.00, not of the 4,400.00 reported
    assert priced.rebate.position_before == Decimal(20_000)
    assert priced.rebate.position_after == Decimal("25500.00")
    assert (priced.margin.revenue, priced.margin.gross_revenue, priced.margin.rebate) == (
        Decimal("4400.00"), Decimal("5500.00"), Decimal("550.00"),
    )
    assert (priced.margin.platform_cost, priced.margin.margin) == (Decimal("1100.00"), Decimal("2750.00"))


def test_the_gross_not_the_target_crosses_a_bracket() -> None:
    # 2,000,000 served at 5.00 € is a gross of 10,000 €; the target of 1,600,000 would be worth only 8,000 €.
    flight = target_facts(contracted_impressions=1_600_000, delivered_impressions=2_000_000, reported_revenue="8000.00")

    (priced,) = price_flights(
        [deal_schedule(TEN_THEN_FIFTEEN)], PlatformRates(system=SYSTEM_RATE), [flight], AFTER_NOVEMBER,
        opening_positions={DEAL_COUNTER: Decimal(95_000)},
    )

    # 5,000 € at 10 % up to 100,000 € and 5,000 € at 15 % above.
    assert [(charge.amount, charge.rate) for charge in priced.rebate.charges] == [
        (Decimal(5_000), Decimal("0.10")), (Decimal(5_000), Decimal("0.15")),
    ]
    assert priced.rebate.rebate == Decimal(1_250)
    assert priced.rebate.position_after == Decimal(105_000)


def test_a_running_target_flight_is_priced_on_its_gross_to_date_and_does_not_advance_the_counter() -> None:
    closed = target_facts(
        flight_id=1, flight_start=date(2026, 11, 1), flight_end=date(2026, 11, 5), delivered_impressions=600_000,
        reported_revenue="2400.00", buyer_spend="3000.00",
    )
    running = target_facts(
        flight_id=2, flight_start=date(2026, 11, 1), flight_end=date(2026, 11, 30), delivered_impressions=400_000,
        reported_revenue="1600.00", buyer_spend="2000.00",
    )

    first, second = price_flights(
        [deal_schedule()], PlatformRates(system=SYSTEM_RATE), [running, closed], date(2026, 11, 10)
    )

    assert (first.facts.flight_id, second.facts.flight_id) == (1, 2)
    # The closed flight's position does not include the running flight's gross.
    assert (first.rebate.position_before, first.rebate.position_after) == (Decimal(0), Decimal("3000.00"))
    assert second.margin.status is FlightStatus.RUNNING
    assert second.rebate.rebate == Decimal("200.00")  # 10 % of the gross to date, 2,000.00
    assert second.margin.rebate == Decimal("200.00")  # not pro-rated by 10 of 30 days
    assert second.rebate.position_before == second.rebate.position_after == Decimal("3000.00")


def test_a_committed_flight_still_accrues_its_contracted_revenue_whatever_it_reports() -> None:
    plain = price_flights([schedule()], PlatformRates(system=SYSTEM_RATE), [facts()], AS_OF)
    reporting = price_flights(
        [schedule()], PlatformRates(system=SYSTEM_RATE),
        [replace(facts(), reported_revenue=Decimal("1.00"), buyer_spend=Decimal("99999.00"))], AS_OF,
    )

    assert reporting == tuple(replace(priced, facts=replace(priced.facts, reported_revenue=Decimal("1.00"),
                                                            buyer_spend=Decimal("99999.00"))) for priced in plain)
    assert plain[0].rebate.position_after == Decimal("3631.01")
