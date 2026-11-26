"""A line total is the exact sum of its flights' rounded amounts; a campaign total, of its lines'."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from app.domain.services.flight_margin import calculate_flight_margin
from app.domain.services.margin_totals import total_flights, total_lines
from app.domain.value_objects.margin import FlightMargin
from app.domain.value_objects.volume_commitment import VolumeCommitment
from tests.fixtures.flight_inputs import flight_economics

AS_OF = date(2026, 9, 10)


def _flight(
    flight_start: date,
    flight_end: date,
    contracted_impressions: int = 1000,
    sale_cpm: str = "10.00",
    delivered_impressions: int = 0,
    media_cost: str = "0.00",
    rebate_amount: str = "0",
) -> FlightMargin:
    return calculate_flight_margin(
        flight_economics(
            flight_start=flight_start,
            flight_end=flight_end,
            contracted_impressions=contracted_impressions,
            sale_cpm=Decimal(sale_cpm),
            delivered_impressions=delivered_impressions,
            media_cost=Decimal(media_cost),
            rebate_amount=Decimal(rebate_amount),
            platform_rate=Decimal("1.00"),
        ),
        as_of=AS_OF,
    )


def _closed(**values: object) -> FlightMargin:
    return _flight(date(2026, 8, 1), date(2026, 8, 31), **values)  # type: ignore[arg-type]


def test_a_line_total_is_the_sum_of_the_rounded_amounts_not_the_rounded_sum():
    # Each flight is 10.004 € exactly: it rounds to 10.00 €. Three of them add to 30.00 €; rounding the
    # unrounded sum (30.012 €) would give 30.01 €.
    flights = [_closed(sale_cpm="10.004") for _ in range(3)]

    total = total_flights(flights)

    assert [flight.revenue for flight in flights] == [Decimal("10.00")] * 3
    assert total.revenue == Decimal("30.00")
    assert total.margin == Decimal("30.00")


def test_the_total_has_every_term_and_the_margin_is_their_difference():
    flights = [
        _closed(contracted_impressions=726_202, sale_cpm="5.00", delivered_impressions=700_000,
                media_cost="1200.00", rebate_amount="907.7525"),
        _closed(contracted_impressions=1000, sale_cpm="10.00", delivered_impressions=1000, media_cost="2.50"),
    ]

    total = total_flights(flights)

    assert total.revenue == Decimal("3641.01")
    assert total.media_cost == Decimal("1202.50")
    assert total.rebate == Decimal("907.75")
    assert total.platform_cost == Decimal("701.00")
    assert total.margin == Decimal("829.76")
    assert total.margin == total.revenue - total.media_cost - total.rebate - total.platform_cost


def test_every_total_is_a_decimal_with_two_places():
    total = total_flights([_closed()])

    for amount in (total.revenue, total.media_cost, total.rebate, total.platform_cost, total.margin):
        assert isinstance(amount, Decimal)
        assert amount.as_tuple().exponent == -2


def test_a_line_without_flights_totals_zero():
    total = total_flights([])

    assert total.revenue == Decimal("0.00")
    assert total.margin == Decimal("0.00")
    assert total.provisional is False
    assert total.flights_counted == 0


def test_a_line_with_a_closed_flight_a_running_one_and_one_not_started():
    closed = _closed()  # August, closed: revenue 10.00
    running = _flight(date(2026, 9, 1), date(2026, 9, 30), contracted_impressions=3000)  # 30 EUR x 10/30 = 10.00
    not_started = _flight(date(2026, 10, 1), date(2026, 10, 31), contracted_impressions=5000)

    total = total_flights([closed, running, not_started])

    assert total.revenue == Decimal("20.00")
    assert total.flights_counted == 2
    assert total.not_started_count == 1
    assert total.provisional is True


def test_a_line_of_closed_flights_only_is_not_provisional():
    total = total_flights([_closed(), _closed()])

    assert total.provisional is False


def test_a_not_started_flight_alone_does_not_make_a_line_provisional():
    total = total_flights([_closed(), _flight(date(2026, 10, 1), date(2026, 10, 31))])

    assert total.provisional is False
    assert total.not_started_count == 1


def test_a_below_cost_flight_is_counted_and_still_in_the_total():
    healthy = _closed()  # margin 10.00
    loss = _closed(media_cost="25.00")  # revenue 10.00, media cost 25.00: margin -15.00

    total = total_flights([healthy, loss])

    assert loss.below_cost is True
    assert total.below_cost_count == 1
    assert total.margin == Decimal("-5.00")
    assert total.media_cost == Decimal("25.00")


def test_a_campaign_total_is_the_sum_of_its_lines():
    first_line = total_flights([_closed(), _closed(media_cost="25.00")])
    second_line = total_flights([_flight(date(2026, 9, 1), date(2026, 9, 30), contracted_impressions=3000)])

    campaign = total_lines([first_line, second_line])

    assert campaign.revenue == first_line.revenue + second_line.revenue
    assert campaign.margin == first_line.margin + second_line.margin
    assert campaign.flights_counted == 3
    assert campaign.below_cost_count == 1
    assert campaign.provisional is True


def test_a_campaign_of_closed_lines_is_not_provisional():
    campaign = total_lines([total_flights([_closed()]), total_flights([_closed()])])

    assert campaign.provisional is False


def test_a_campaign_total_equals_the_sum_of_all_its_flights():
    flights_by_line = [[_closed(sale_cpm="10.004")] * 2, [_closed(sale_cpm="10.004")]]

    campaign = total_lines([total_flights(flights) for flights in flights_by_line])

    assert campaign.revenue == Decimal("30.00")


def test_a_flight_whose_rebate_and_platform_cost_make_its_margin_negative_is_counted_at_line_and_campaign():
    # Media cost 8.00 against revenue 10.00, but a 50 % rebate (5.00) takes the final margin to -3.00.
    negative = _closed(media_cost="8.00", rebate_amount="5.00")
    healthy = _closed()

    line = total_flights([negative, healthy])
    campaign = total_lines([line])

    assert negative.margin == Decimal("-3.00") and negative.below_cost is True
    assert (line.below_cost_count, campaign.below_cost_count) == (1, 1)
    assert line.margin == Decimal("7.00")  # -3.00 + 10.00: the flagged flight keeps its true value


def _economics(metric: str, delivered: str, impressions: int, contracted: int = 1000) -> FlightMargin:
    return calculate_flight_margin(
        flight_economics(
            flight_start=date(2026, 8, 1), flight_end=date(2026, 8, 31), contracted_impressions=contracted,
            sale_cpm=Decimal("10.00"), delivered_impressions=impressions, media_cost=Decimal("0.00"),
            rebate_amount=Decimal("0"), platform_rate=Decimal("1.00"),
            delivery_metric=metric, delivered=Decimal(delivered),
        ),
        as_of=AS_OF,
    )


def test_a_line_sums_the_delivered_volume_exactly_and_keeps_its_one_metric() -> None:
    total = total_flights([_economics("ots", "280000.5000", 12_000), _economics("ots", "1499.2500", 30)])

    assert total.delivered == Decimal("281499.7500")
    assert total.delivered_impressions == 12_030
    assert total.delivery_metric == "ots"
    assert total.contracted_impressions == 2_000


def test_a_campaign_sums_the_delivered_volume_of_its_lines_and_keeps_the_metric() -> None:
    line_a = total_flights([_economics("ots", "280000.5000", 12_000)])
    line_b = total_flights([_economics("ots", "1499.2500", 30)])

    total = total_lines([line_a, line_b])

    assert total.delivered == Decimal("281499.7500") and total.delivery_metric == "ots"
    assert total.delivered_impressions == 12_030 and total.contracted_impressions == 2_000


def test_totals_of_lines_counted_in_impressions_are_summed_with_the_metric_impressions() -> None:
    total = total_lines([
        total_flights([_economics("impressions", "500", 500)]),
        total_flights([_economics("impressions", "250", 250)]),
    ])

    assert (total.delivery_metric, total.delivered, total.contracted_impressions) == ("impressions", Decimal(750), 2_000)


def test_mixed_metrics_have_no_metric_no_delivered_and_no_contracted_but_real_impressions_and_amounts() -> None:
    dooh = total_flights([_economics("ots", "280000.5000", 12_000, contracted=300_000)])
    ctv = total_flights([_economics("impressions", "198800", 198_800, contracted=200_000)])

    total = total_lines([dooh, ctv])

    assert total.delivery_metric is None and total.delivered is None and total.contracted_impressions is None
    assert total.delivered_impressions == 210_800
    assert total.revenue == dooh.revenue + ctv.revenue
    assert total.platform_cost == dooh.platform_cost + ctv.platform_cost


def test_no_lines_total_zero_without_a_metric() -> None:
    total = total_lines([])

    assert total.delivery_metric is None and total.delivered == 0 and total.contracted_impressions == 0


# --- The gross, the commitment and the two flags at every level (finance/margin-reporting) -------------------------

def _target(
    delivered_impressions: int = 1_100_000,
    sale_cpm: str = "5.00",
    reported_revenue: str = "4400.00",
    buyer_spend: str = "5500.00",
    data_cost: str = "0",
    flight_start: date = date(2026, 8, 1),
    flight_end: date = date(2026, 8, 31),
) -> FlightMargin:
    return calculate_flight_margin(
        flight_economics(
            flight_start=flight_start, flight_end=flight_end, contracted_impressions=1_000_000,
            sale_cpm=Decimal(sale_cpm), delivered_impressions=delivered_impressions, media_cost=Decimal(0),
            rebate_amount=Decimal(0), platform_rate=Decimal("1.00"), volume_commitment=VolumeCommitment.TARGET,
            reported_revenue=Decimal(reported_revenue), buyer_spend=Decimal(buyer_spend), data_cost=Decimal(data_cost),
        ),
        as_of=AS_OF,
    )


def test_a_line_sums_the_gross_of_its_target_flights_exactly() -> None:
    # 1,100,000 at 5.00 € and 333,333 at 3.333 € (1,110.998889 rounds to 1,111.00): the sum of the rounded grosses.
    closed = _target()
    running = _target(
        delivered_impressions=333_333, sale_cpm="3.333", flight_start=date(2026, 9, 1), flight_end=date(2026, 9, 30)
    )

    total = total_flights([closed, running])

    assert (closed.gross_revenue, running.gross_revenue) == (Decimal("5500.00"), Decimal("1111.00"))
    assert total.gross_revenue == Decimal("6611.00")
    assert total.volume_commitment is VolumeCommitment.TARGET


def test_a_line_of_committed_flights_has_no_gross_and_is_committed() -> None:
    total = total_flights([_closed(), _closed()])

    assert total.gross_revenue is None
    assert total.volume_commitment is VolumeCommitment.COMMITTED
    assert (total.gross_differs_count, total.data_cost_count) == (0, 0)


def test_a_target_line_whose_flights_have_not_started_has_its_commitment_and_no_gross() -> None:
    total = total_flights([_target(flight_start=date(2026, 10, 1), flight_end=date(2026, 10, 31))])

    assert total.volume_commitment is VolumeCommitment.TARGET
    assert total.gross_revenue is None
    assert total.not_started_count == 1


def test_a_line_counts_the_flights_carrying_each_flag() -> None:
    differs = _target(buyer_spend="6050.00")
    data_cost = _target(data_cost="1.25")
    plain = _target()

    total = total_flights([differs, data_cost, plain])

    assert (differs.gross_differs_from_buyer_spend, data_cost.data_cost_reported) == (True, True)
    assert (total.gross_differs_count, total.data_cost_count) == (1, 1)
    # No amount changes because of the flags.
    assert total.revenue == Decimal("13200.00")
    assert plain.margin is not None and total.margin == plain.margin * 3


def test_a_campaign_of_both_commitments_has_no_commitment_and_the_gross_of_its_target_line() -> None:
    target_line = total_flights([_target(data_cost="1.25")])
    committed_line = total_flights([_closed()])

    campaign = total_lines([target_line, committed_line])

    assert campaign.volume_commitment is None
    assert campaign.gross_revenue == Decimal("5500.00")
    assert campaign.data_cost_count == 1


def test_a_campaign_of_target_lines_only_is_target_and_sums_their_gross() -> None:
    campaign = total_lines([total_flights([_target()]), total_flights([_target(delivered_impressions=1_000)])])

    assert campaign.volume_commitment is VolumeCommitment.TARGET
    assert campaign.gross_revenue == Decimal("5505.00")


def test_a_campaign_of_committed_lines_only_is_committed_and_has_no_gross() -> None:
    campaign = total_lines([total_flights([_closed()]), total_flights([_closed()])])

    assert campaign.volume_commitment is VolumeCommitment.COMMITTED
    assert campaign.gross_revenue is None


def test_the_flags_are_counted_at_the_line_the_campaign_and_the_totals() -> None:
    line = total_flights([_target(buyer_spend="6050.00"), _target(data_cost="1.25")])
    campaign = total_lines([line])
    totals = total_lines([campaign, total_lines([total_flights([_closed()])])])

    for level in (line, campaign, totals):
        assert (level.gross_differs_count, level.data_cost_count) == (1, 1)


def test_the_totals_over_a_campaign_of_both_commitments_and_a_target_campaign_have_no_commitment() -> None:
    # The campaign of both commitments carries null; above it, null is a disagreement, not the absence of flights.
    both = total_lines([total_flights([_target()]), total_flights([_closed()])])
    target_only = total_lines([total_flights([_target()])])

    totals = total_lines([both, target_only])

    assert both.volume_commitment is None
    assert totals.volume_commitment is None
    assert totals.gross_revenue == Decimal("11000.00")


def test_a_line_or_campaign_with_no_flights_does_not_change_the_commitment_above_it() -> None:
    campaign = total_lines([total_flights([_target()]), total_flights([])])

    assert campaign.volume_commitment is VolumeCommitment.TARGET


def test_no_flights_and_no_lines_have_no_commitment_no_gross_and_no_flag() -> None:
    for total in (total_flights([]), total_lines([])):
        assert (total.volume_commitment, total.gross_revenue) == (None, None)
        assert (total.gross_differs_count, total.data_cost_count) == (0, 0)


def test_totals_over_a_campaign_that_already_mixes_metrics_are_null() -> None:
    # Registration refuses such a campaign (mixed_delivery_metrics), but the totals do not assume it: its null metric
    # is a mix, not the absence of flights, so the totals cannot carry the OTS campaign's metric and partial sums.
    mixed = total_lines([
        total_flights([_economics("ots", "280000.5", 12_000, contracted=300_000)]),
        total_flights([_economics("impressions", "198800", 198_800, contracted=200_000)]),
    ])
    ots = total_lines([total_flights([_economics("ots", "1000", 10, contracted=5_000)])])

    totals = total_lines([mixed, ots])

    assert (mixed.delivery_metric, mixed.contracted_impressions, mixed.delivered) == (None, None, None)
    assert (totals.delivery_metric, totals.contracted_impressions, totals.delivered) == (None, None, None)
    assert totals.delivered_impressions == 12_000 + 198_800 + 10
    assert totals.revenue == mixed.revenue + ots.revenue


def test_a_level_with_no_flights_does_not_null_the_metric_above_it() -> None:
    totals = total_lines([total_lines([]), total_lines([total_flights([_economics("ots", "1000", 10, contracted=5_000)])])])

    assert (totals.delivery_metric, totals.contracted_impressions, totals.delivered) == ("ots", 5_000, Decimal("1000"))


# --- The change warning of a closed flight is only counted (finance/margin-reporting) -------------------------------


def test_a_flight_is_not_flagged_as_changed_after_its_closing_by_default() -> None:
    assert _closed().delivery_changed is False
    assert _flight(date(2026, 9, 1), date(2026, 9, 30)).delivery_changed is False


def test_a_line_and_a_campaign_count_the_flights_flagged_as_changed_after_closing() -> None:
    flagged = replace(_closed(), delivery_changed=True)
    line = total_flights([flagged, _closed(), flagged])
    other = total_flights([_closed()])

    campaign = total_lines([line, other])

    assert line.delivery_changed_count == 2
    assert other.delivery_changed_count == 0
    assert campaign.delivery_changed_count == 2
    assert total_lines([]).delivery_changed_count == 0


def test_the_change_warning_changes_no_other_figure_of_a_total() -> None:
    flights = [
        _closed(contracted_impressions=726_202, sale_cpm="5.00", delivered_impressions=700_000, media_cost="1200.00",
                rebate_amount="907.7525"),
        _flight(date(2026, 9, 1), date(2026, 9, 30), delivered_impressions=1000, media_cost="2.50"),
        _flight(date(2026, 10, 1), date(2026, 10, 31)),
    ]
    flagged = [replace(flights[0], delivery_changed=True), *flights[1:]]

    plain_line, flagged_line = total_flights(flights), total_flights(flagged)
    plain_campaign, flagged_campaign = total_lines([plain_line]), total_lines([flagged_line])

    assert replace(flagged_line, delivery_changed_count=0) == plain_line
    assert replace(flagged_campaign, delivery_changed_count=0) == plain_campaign
    assert (flagged_line.delivery_changed_count, flagged_campaign.delivery_changed_count) == (1, 1)
