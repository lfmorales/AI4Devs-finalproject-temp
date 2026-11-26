"""The closed month through the database and the API: four real rows and a line without a price.

The rows are chosen from the private sheet by what they are (a normal one, one without a rebate schedule, one that
delivered more than contracted, one with a negative margin and positive revenue), then created in the test
database, closed with POST /margin/closings and read back with GET /margin.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.delivery_ingestion_service import DeliveryIngestionService
from app.domain.value_objects.delivery import DeliveryDateRange, ExternalLineKey
from app.infrastructure.persistence.models.campaign import CampaignLineRecord, CampaignRecord
from app.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from app.presentation.dependencies import providers
from tests.acceptance.closed_month_sheet import (
    SHEET_PATH,
    SKIP_REASON,
    SheetRow,
    load_rows,
    price_rows,
    split_rows,
)
from tests.fixtures.delivery_data import (
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    insert_mapping,
    seeded_dsp_id,
)
from tests.fixtures.delivery_rows import dsp_row
from tests.fixtures.dsp_delivery_client import InMemoryDspDeliveryClient
from tests.fixtures.margin_data import group_of, set_volume

pytestmark = pytest.mark.skipif(not SHEET_PATH.exists(), reason=SKIP_REASON)

CENT = Decimal("0.01")
AMOUNTS = ("revenue", "media_cost", "rebate", "platform_cost", "margin")
SYNTHETIC_NAME = "Synthetic line without a price"


def _storable(row: SheetRow) -> bool:
    """The database holds a sale CPM with two decimals."""
    return row.oc_cpm == row.oc_cpm.quantize(CENT) and row.sale > 0


def _pick(rows: list[SheetRow], taken: set[int], condition) -> SheetRow:
    for row in rows:
        if row.number not in taken and _storable(row) and condition(row):
            taken.add(row.number)
            return row
    pytest.skip("the sheet has no row of this kind with a CPM of two decimals")


@pytest.fixture(scope="module")
def chosen() -> dict[str, SheetRow]:
    compared, _ = split_rows(load_rows())
    taken: set[int] = set()
    return {
        "normal": _pick(compared, taken, lambda r: r.rebate_rate is not None and r.margin > 0 and r.served_impressions <= r.contracted_impressions),
        "without rebate": _pick(compared, taken, lambda r: r.rebate_rate is None),
        "over-delivery": _pick(compared, taken, lambda r: r.served_impressions > r.contracted_impressions and r.rebate_rate is not None),
        "negative margin": _pick(compared, taken, lambda r: r.margin < 0),
    }


@pytest.fixture
def month(client_for_roles, test_db_session, chosen):
    """The five lines created, their schedules and platform rates set through the API, and the month closed."""
    finance = client_for_roles("finance")
    operations = client_for_roles("operations")  # rates and schedules are set by operations only
    finance.app.dependency_overrides[providers.get_today] = lambda: date(2026, 9, 1)
    batch = insert_ingestion_batch(test_db_session)

    def create(name: str, contracted: int, cpm: str, served: int, cost: Decimal, platform_cpm: str, rebate_rate: str | None):
        line_id = insert_campaign_line(test_db_session, campaign_name=name)
        set_volume(test_db_session, line_id, contracted, cpm)
        insert_delivery(test_db_session, line_id, date(2026, 8, 10), served, batch, cost)
        assert operations.post("/margin/platform-rates", json={
            "level": "line", "campaign_line_id": line_id, "rate_per_thousand": platform_cpm}).status_code == 201
        if rebate_rate is not None:
            assert operations.post("/margin/rebate-schedules", json={
                "holding_group_id": group_of(test_db_session, line_id), "valid_from": "2026-01-01",
                "brackets": [{"lower": "0", "upper": None, "rate": rebate_rate}]}).status_code == 201

    for row in chosen.values():
        create(row.campaign, row.contracted_impressions, str(row.oc_cpm), row.served_impressions, row.purchase_cost,
               str(row.platform_cpm), None if row.rebate_rate is None else str(row.rebate_rate))
    # A platform rate other than the system one, so that ignoring the line override would show.
    create(SYNTHETIC_NAME, 500_000, "0.00", 400_000, Decimal("120.00"), "2.50", None)

    closed = finance.post("/margin/closings", json={"year": 2026, "month": 8}).json()
    return finance, closed


def _flight_of(body: dict, name: str) -> tuple[dict, dict, dict]:
    (campaign,) = [c for c in body["campaigns"] if c["name"] == name]
    (line,) = campaign["lines"]
    (flight,) = line["flights"]
    return campaign, line, flight


def test_the_month_closes_the_five_flights(month):
    _, closed = month

    assert closed == {"year": 2026, "month": 8, "closed": 5, "already_closed": 0, "closings": 1}


def test_each_real_row_reads_back_with_the_amounts_of_the_domain_and_of_the_sheet(month, chosen):
    finance, _ = month
    body = finance.get("/margin").json()
    expected = price_rows(list(chosen.values()))

    for label, row in chosen.items():
        _, _, flight = _flight_of(body, row.campaign)
        margin = expected[row.number].margin
        assert flight["state"] == "closed", label
        assert [flight[name] for name in AMOUNTS] == [str(getattr(margin, name)) for name in AMOUNTS], label
        # The sheet billed at the lesser of served and contracted (committed-billing-and-review): the "normal" row
        # served less than it contracted, so it departs from the sheet's own sale; the others still match it.
        assert abs(Decimal(flight["revenue"]) - row.expected_revenue) <= CENT, label
        assert abs(Decimal(flight["media_cost"]) - row.purchase_cost) <= CENT, label
        assert abs(Decimal(flight["rebate"]) - row.expected_rebate) <= CENT, label
        assert abs(Decimal(flight["platform_cost"]) - row.sheet_platform_cost) <= CENT, label
        assert abs(Decimal(flight["margin"]) - row.expected_margin) <= Decimal("0.04"), label


def test_the_percentage_and_the_flags_of_the_real_rows(month, chosen):
    finance, _ = month
    body = finance.get("/margin").json()

    for label, row in chosen.items():
        _, line, flight = _flight_of(body, row.campaign)
        expected_pct = row.expected_margin / row.expected_revenue * 100
        assert abs(Decimal(flight["margin_pct"]) - expected_pct) <= Decimal("0.05"), label
        assert flight["zero_sale"] is False and line["zero_sale"] is False, label
        assert flight["below_cost"] is (row.expected_margin < 0), label


def test_the_row_without_a_rebate_schedule_has_an_explicit_zero(month, chosen):
    finance, _ = month

    _, _, flight = _flight_of(finance.get("/margin").json(), chosen["without rebate"].campaign)

    assert flight["rebate"] == "0.00"
    assert flight["rates"]["rebate_step"] == 8 and flight["rates"]["zero_reason"] is not None


def test_the_over_delivery_does_not_raise_the_revenue(month, chosen):
    finance, _ = month
    row = chosen["over-delivery"]

    _, _, flight = _flight_of(finance.get("/margin").json(), row.campaign)

    assert abs(Decimal(flight["revenue"]) - row.sale) <= CENT
    assert row.served_impressions > row.contracted_impressions


def test_the_line_without_a_price_has_no_revenue_no_rebate_and_no_percentage(month):
    finance, _ = month

    campaign, line, flight = _flight_of(finance.get("/margin").json(), SYNTHETIC_NAME)

    assert (flight["revenue"], flight["rebate"], flight["media_cost"], flight["platform_cost"], flight["margin"]) == (
        "0.00", "0.00", "120.00", "1000.00", "-1120.00")
    assert flight["margin_pct"] is None and line["totals"]["margin_pct"] is None and campaign["totals"]["margin_pct"] is None
    assert flight["zero_sale"] is True and line["zero_sale"] is True and campaign["zero_sale"] is True
    assert flight["below_cost"] is True


def test_every_amount_leaves_as_a_decimal_string_and_the_totals_count_the_flags(month):
    finance, _ = month
    body = finance.get("/margin").json()

    for campaign in body["campaigns"]:
        for line in campaign["lines"]:
            for flight in line["flights"]:
                assert all(isinstance(flight[name], str) for name in AMOUNTS)
                assert flight["margin_pct"] is None or isinstance(flight["margin_pct"], str)
    assert body["totals"]["zero_sale_count"] == 1
    assert body["totals"]["flights_counted"] == 5
    assert body["totals"]["below_cost_count"] >= 2  # the negative-margin row and the line without a price



# --- The closed month does not move when its window is ingested again (finance/margin-reporting) --------------------

WARNING_FIELDS = ("delivery_changed", "delivery_change", "delivery_changed_count")


def _without_the_warning(value: Any) -> Any:
    """The response with the change warning left out: every other figure must stay as the closing froze it."""
    if isinstance(value, dict):
        return {key: _without_the_warning(item) for key, item in value.items() if key not in WARNING_FIELDS}
    if isinstance(value, list):
        return [_without_the_warning(item) for item in value]
    return value


def _line_of(session: Session, campaign_name: str) -> int:
    return session.scalars(
        select(CampaignLineRecord.id).join(CampaignRecord, CampaignRecord.id == CampaignLineRecord.campaign_id)
        .where(CampaignRecord.name == campaign_name)
    ).one()


def test_a_closed_month_reads_the_same_after_its_window_is_ingested_again_with_other_figures(
    month: tuple[Any, dict[str, Any]], chosen: dict[str, SheetRow], test_db_session: Session
) -> None:
    finance, _ = month
    before = finance.get("/margin").json()
    restated = {chosen["normal"].campaign, chosen["negative margin"].campaign}
    rows = []
    for name in [row.campaign for row in chosen.values()] + [SYNTHETIC_NAME]:
        line_id = _line_of(test_db_session, name)
        key = ExternalLineKey(f"campaign-{line_id}", f"line-{line_id}")
        insert_mapping(test_db_session, line_id, seeded_dsp_id(test_db_session), key.external_campaign_id,
                       key.external_line_item_id)
        (flight,) = _flight_of(before, name)[2:]
        impressions, cost = flight["delivered_impressions"], Decimal(flight["media_cost"])
        if name in restated:
            # The DSP restates the day: twice the impressions and 777.77 € more of cost.
            impressions, cost = impressions * 2, cost + Decimal("777.77")
        rows.append(dsp_row(date(2026, 8, 10), key, impressions=impressions, media_cost=cost))

    # The window of the closed month is ingested again, through the ingestion service, as a custom range would.
    result = DeliveryIngestionService(
        InMemoryDspDeliveryClient(rows), lambda: SqlAlchemyUnitOfWork(lambda: test_db_session),
        lambda: datetime(2026, 9, 2, 2, 0),
    ).run(seeded_dsp_id(test_db_session), date(2026, 9, 2), window=DeliveryDateRange(date(2026, 8, 1), date(2026, 8, 31)))
    after = finance.get("/margin").json()

    assert result.stored_row_count == len(rows)
    assert _without_the_warning(after) == _without_the_warning(before)
    flagged = {
        campaign["name"] for campaign in after["campaigns"] for line in campaign["lines"] for flight in line["flights"]
        if flight["delivery_changed"]
    }
    assert flagged == restated
    for campaign in after["campaigns"]:
        (line,) = campaign["lines"]
        (flight,) = line["flights"]
        expected = 1 if campaign["name"] in restated else 0
        assert (line["totals"]["delivery_changed_count"], campaign["totals"]["delivery_changed_count"]) == (
            expected, expected,
        )
        assert flight["delivery_change"]["delivered_impressions_difference"] == (
            flight["delivered_impressions"] if campaign["name"] in restated else 0
        )
    assert (before["totals"]["delivery_changed_count"], after["totals"]["delivery_changed_count"]) == (0, 2)
