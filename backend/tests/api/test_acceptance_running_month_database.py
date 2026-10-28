"""A month still running through the database and the API: four real rows and a line without a price.

The windows are moved so that one `as_of` serves every row: a row's flight starts `days_served` days before it, so the
contract days elapsed are the days the sheet says were served, and ends `days_oc` days after its start. The month is
closed for what has ended and the rest is read as it stands.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.presentation.dependencies import providers
from tests.acceptance.running_month_sheet import (
    SHEET_PATH,
    SKIP_REASON,
    SheetRow,
    load_rows,
    price_row,
    split_rows,
)
from tests.fixtures.delivery_data import insert_campaign_line, insert_delivery, insert_ingestion_batch, replace_flights
from tests.fixtures.margin_data import group_of, set_volume

pytestmark = pytest.mark.skipif(not SHEET_PATH.exists(), reason=SKIP_REASON)

AS_OF = date(2026, 10, 25)
TODAY = AS_OF + timedelta(days=1)
CENT = Decimal("0.01")
AMOUNTS = ("revenue", "media_cost", "rebate", "platform_cost", "margin")
SYNTHETIC_NAME = "Synthetic line without a price"


def _start(row: SheetRow) -> date:
    return AS_OF - timedelta(days=row.days_served - 1)


def _end(row: SheetRow) -> date:
    return _start(row) + timedelta(days=row.days_oc - 1)


def _fits(row: SheetRow) -> bool:
    """The flight must lie inside October, and the sale must be storable with two decimals of CPM."""
    return _start(row).month == 10 and _end(row).month == 10 and _start(row) >= date(2026, 10, 1)


def _pick(rows: list[SheetRow], taken: set[int], condition) -> SheetRow:
    for row in rows:
        if row.number not in taken and _fits(row) and condition(row):
            taken.add(row.number)
            return row
    pytest.skip("the sheet has no row of this kind that fits in October with this as_of")


@pytest.fixture(scope="module")
def chosen() -> dict[str, SheetRow]:
    compared = split_rows(load_rows())[0]
    taken: set[int] = set()
    return {
        "running with sale": _pick(compared, taken, lambda r: not r.is_closed and r.rebate_rate is not None),
        "closed": _pick(compared, taken, lambda r: r.is_closed and r.rebate_rate is not None and r.served_impressions <= r.contracted_impressions),
        "running without rebate": _pick(compared, taken, lambda r: not r.is_closed and r.rebate_rate is None),
        "over-delivery": _pick(compared, taken, lambda r: r.served_impressions > r.contracted_impressions and r.rebate_rate is not None),
    }


@pytest.fixture
def month(client_for_roles, test_db_session, chosen):
    finance = client_for_roles("finance")
    finance.app.dependency_overrides[providers.get_today] = lambda: TODAY
    batch = insert_ingestion_batch(test_db_session)

    def create(name, start, end, contracted, cpm, served, cost, platform_rate, rebate_rate):
        line_id = insert_campaign_line(test_db_session, campaign_name=name, start_date=start, end_date=end)
        replace_flights(test_db_session, line_id, [(start, end)])
        set_volume(test_db_session, line_id, contracted, cpm)
        insert_delivery(test_db_session, line_id, start, served, batch, cost)
        assert finance.post("/margin/platform-rates", json={
            "level": "line", "campaign_line_id": line_id, "rate_per_thousand": platform_rate}).status_code == 201
        if rebate_rate is not None:
            assert finance.post("/margin/rebate-schedules", json={
                "holding_group_id": group_of(test_db_session, line_id), "valid_from": "2026-01-01",
                "brackets": [{"lower": "0", "upper": None, "rate": rebate_rate}]}).status_code == 201

    for row in chosen.values():
        create(row.campaign, _start(row), _end(row), row.contracted_impressions, str(row.oc_cpm), row.served_impressions,
               row.purchase_cost, str(row.platform_rate.quantize(Decimal("0.000001"))),
               None if row.rebate_rate is None else str(row.rebate_rate))
    # A platform rate other than the system one, so that ignoring the line override would show.
    create(SYNTHETIC_NAME, date(2026, 10, 1), date(2026, 10, 31), 500_000, "0.00", 400_000, Decimal("120.00"), "2.50", None)

    closed = finance.post("/margin/closings", json={"year": 2026, "month": 10}).json()
    return finance, closed


def _flight_of(body: dict, name: str) -> tuple[dict, dict, dict]:
    (campaign,) = [c for c in body["campaigns"] if c["name"] == name]
    (line,) = campaign["lines"]
    (flight,) = line["flights"]
    return campaign, line, flight


def test_only_the_flights_that_have_ended_are_closed(month, chosen):
    _, closed = month

    assert closed == {"year": 2026, "month": 10, "closed": sum(1 for r in chosen.values() if r.is_closed), "already_closed": 0}


def test_each_real_row_reads_back_with_the_amounts_of_the_domain_and_of_the_sheet(month, chosen):
    finance, _ = month
    body = finance.get("/margin").json()

    for label, row in chosen.items():
        _, _, flight = _flight_of(body, row.campaign)
        margin = price_row(row, flight_start=_start(row), as_of=AS_OF).margin
        assert [flight[name] for name in AMOUNTS] == [str(getattr(margin, name)) for name in AMOUNTS], label
        assert abs(Decimal(flight["revenue"]) - row.accrued_revenue) <= CENT, label
        assert abs(Decimal(flight["rebate"]) - row.accrued_rebate) <= CENT, label
        assert abs(Decimal(flight["media_cost"]) - row.purchase_cost) <= CENT, label
        assert abs(Decimal(flight["platform_cost"]) - row.platform_cost) <= CENT, label
        assert abs(Decimal(flight["margin"]) - row.expected_margin) <= Decimal("0.04"), label


def test_the_state_and_the_provisional_flag_follow_the_days(month, chosen):
    finance, _ = month
    body = finance.get("/margin").json()

    for label, row in chosen.items():
        _, _, flight = _flight_of(body, row.campaign)
        assert flight["state"] == ("closed" if row.is_closed else "running"), label
        assert flight["provisional"] is (not row.is_closed), label


def test_the_percentage_matches_the_actual_one_of_the_sheet(month, chosen):
    finance, _ = month
    body = finance.get("/margin").json()

    for label, row in chosen.items():
        _, _, flight = _flight_of(body, row.campaign)
        assert abs(Decimal(flight["margin_pct"]) - row.margin_pct_actual * 100) <= Decimal("0.05"), label
        assert flight["zero_sale"] is False, label


def test_the_row_without_a_rebate_schedule_has_an_explicit_zero(month, chosen):
    finance, _ = month

    _, _, flight = _flight_of(finance.get("/margin").json(), chosen["running without rebate"].campaign)

    assert flight["rebate"] == "0.00"
    assert flight["rates"]["rebate_step"] == 8 and flight["rates"]["zero_reason"] is not None
    assert flight["state"] == "running" and flight["provisional"] is True


def test_the_over_delivery_does_not_raise_the_accrued_revenue(month, chosen):
    finance, _ = month
    row = chosen["over-delivery"]

    _, _, flight = _flight_of(finance.get("/margin").json(), row.campaign)

    assert row.served_impressions > row.contracted_impressions
    assert abs(Decimal(flight["revenue"]) - row.accrued_revenue) <= CENT


def test_the_line_without_a_price_accrues_no_revenue_and_stays_provisional(month):
    finance, _ = month

    campaign, line, flight = _flight_of(finance.get("/margin").json(), SYNTHETIC_NAME)

    assert (flight["revenue"], flight["rebate"], flight["media_cost"], flight["platform_cost"], flight["margin"]) == (
        "0.00", "0.00", "120.00", "1000.00", "-1120.00")
    assert flight["state"] == "running" and flight["provisional"] is True
    assert flight["zero_sale"] is True and line["zero_sale"] is True and campaign["zero_sale"] is True
    assert flight["margin_pct"] is None and campaign["totals"]["margin_pct"] is None
    assert flight["below_cost"] is True


def test_the_totals_are_provisional_decimal_strings_and_count_the_flags(month, chosen):
    finance, _ = month
    body = finance.get("/margin").json()

    for campaign in body["campaigns"]:
        for line in campaign["lines"]:
            for flight in line["flights"]:
                assert all(isinstance(flight[name], str) for name in AMOUNTS)
    assert body["totals"]["provisional"] is True
    assert body["totals"]["flights_counted"] == len(chosen) + 1
    assert body["totals"]["zero_sale_count"] == 1
    assert all(isinstance(body["totals"][name], str) for name in AMOUNTS)
    assert Decimal(body["totals"]["revenue"]) == sum(
        (Decimal(flight["revenue"]) for c in body["campaigns"] for l in c["lines"] for flight in l["flights"]), Decimal(0))
