"""The delivery that counts toward a flight is the line's own, dated inside the flight's window."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from app.domain.services.flight_delivery import deliveries_in_window
from app.domain.value_objects.delivery import DailyDelivery

AUGUST = (date(2026, 8, 1), date(2026, 8, 31))
SEPTEMBER = (date(2026, 9, 1), date(2026, 9, 30))
LINE_ID = 7


def _delivery(day: date, impressions: int = 1000, media_cost: str = "1.50", line_id: int = LINE_ID) -> DailyDelivery:
    return DailyDelivery(
        campaign_line_id=line_id,
        ingestion_batch_id=1,
        delivery_date=day,
        impressions=impressions,
        clicks=0,
        media_cost=Decimal(media_cost),
        measurable_impressions=0,
        viewable_impressions=0,
        banner_size=None,
        screen=None,
        line_format=None,
        ots=Decimal(0),
        video_completions=0,
        buyer_spend=Decimal(0),
        reported_revenue=Decimal(0),
        third_party_data_cost=Decimal(0),
        audience_data_cost=Decimal(0),
    )


def test_a_delivery_counts_only_toward_the_flight_whose_window_holds_it():
    deliveries = [_delivery(date(2026, 8, 20), 500, "1.00"), _delivery(date(2026, 9, 2), 700, "2.00")]

    august = deliveries_in_window(deliveries, LINE_ID, *AUGUST)
    september = deliveries_in_window(deliveries, LINE_ID, *SEPTEMBER)

    assert (august.impressions, august.media_cost) == (500, Decimal("1.00"))
    assert (september.impressions, september.media_cost) == (700, Decimal("2.00"))


def test_both_ends_of_the_window_are_included():
    deliveries = [_delivery(date(2026, 9, 1)), _delivery(date(2026, 9, 30)), _delivery(date(2026, 8, 31)),
                  _delivery(date(2026, 10, 1))]

    september = deliveries_in_window(deliveries, LINE_ID, *SEPTEMBER)

    assert september.impressions == 2000


def test_a_delivery_outside_every_flight_counts_nowhere():
    # A line with flights in August and September and a delivery on October 3rd.
    deliveries = [_delivery(date(2026, 10, 3), 900, "9.00")]

    totals = [deliveries_in_window(deliveries, LINE_ID, *window) for window in (AUGUST, SEPTEMBER)]

    assert [total.impressions for total in totals] == [0, 0]
    assert [total.media_cost for total in totals] == [Decimal("0"), Decimal("0")]


def test_a_delivery_between_two_flights_counts_nowhere():
    # A line paused for a month: flights in July and September, delivery in August.
    deliveries = [_delivery(date(2026, 8, 15), 900, "9.00")]

    july = deliveries_in_window(deliveries, LINE_ID, date(2026, 7, 1), date(2026, 7, 31))
    september = deliveries_in_window(deliveries, LINE_ID, *SEPTEMBER)

    assert july.impressions == september.impressions == 0


def test_another_lines_delivery_never_counts():
    deliveries = [_delivery(date(2026, 9, 2), 700, "2.00", line_id=8)]

    assert deliveries_in_window(deliveries, LINE_ID, *SEPTEMBER).impressions == 0


def test_the_media_cost_is_summed_without_rounding():
    deliveries = [_delivery(date(2026, 9, 1), media_cost="0.333333"), _delivery(date(2026, 9, 2), media_cost="0.333333")]

    september = deliveries_in_window(deliveries, LINE_ID, *SEPTEMBER)

    assert september.media_cost == Decimal("0.666666")
    assert isinstance(september.media_cost, Decimal)


def test_no_delivery_is_a_zero_decimal_cost():
    result = deliveries_in_window([], LINE_ID, *SEPTEMBER)

    assert result.impressions == 0
    assert result.media_cost == Decimal("0")


def _ots_delivery(day: date, ots: str, impressions: int) -> DailyDelivery:
    return replace(_delivery(day, impressions), ots=Decimal(ots))


def test_the_window_delivery_is_summed_in_the_metric_of_the_channel() -> None:
    deliveries = [
        _ots_delivery(date(2026, 8, 20), "40000.2500", 6_000),
        _ots_delivery(date(2026, 8, 21), "240000.2500", 6_000),
        _ots_delivery(date(2026, 9, 2), "999.0000", 1),
    ]

    in_ots = deliveries_in_window(deliveries, LINE_ID, *AUGUST, delivery_metric="ots")
    in_impressions = deliveries_in_window(deliveries, LINE_ID, *AUGUST)

    assert (in_ots.delivered, in_ots.impressions) == (Decimal("280000.5000"), 12_000)
    assert (in_impressions.delivered, in_impressions.impressions) == (Decimal(12_000), 12_000)


# --- The amounts a DSP reports besides its cost: summed exactly inside the window, never rounded here -----------------

def _reported(
    day: date, reported_revenue: str, buyer_spend: str, third_party: str, audience: str, line_id: int = LINE_ID
) -> DailyDelivery:
    return replace(
        _delivery(day, line_id=line_id),
        reported_revenue=Decimal(reported_revenue),
        buyer_spend=Decimal(buyer_spend),
        third_party_data_cost=Decimal(third_party),
        audience_data_cost=Decimal(audience),
    )


def test_the_four_reported_amounts_are_summed_exactly_inside_the_window() -> None:
    deliveries = [
        _reported(date(2026, 9, 1), "1000.123456", "1250.000001", "0.25", "0"),
        _reported(date(2026, 9, 30), "3399.876544", "4249.999999", "0", "1.00"),
        _reported(date(2026, 8, 31), "999", "999", "999", "999"),  # the day before the window
        _reported(date(2026, 10, 1), "999", "999", "999", "999"),  # the day after
        _reported(date(2026, 9, 15), "999", "999", "999", "999", line_id=8),  # another line
    ]

    september = deliveries_in_window(deliveries, LINE_ID, *SEPTEMBER)

    assert september.reported_revenue == Decimal("4400.000000")
    assert september.buyer_spend == Decimal("5500.000000")
    # The two data costs are one amount: only their presence is flagged, never subtracted.
    assert september.data_cost == Decimal("1.25")


def test_no_delivery_reports_zero_decimal_amounts() -> None:
    result = deliveries_in_window([], LINE_ID, *SEPTEMBER)

    assert (result.reported_revenue, result.buyer_spend, result.data_cost) == (Decimal(0), Decimal(0), Decimal(0))
    assert all(isinstance(value, Decimal) for value in (result.reported_revenue, result.buyer_spend, result.data_cost))
