from collections import defaultdict
from collections.abc import Callable
from datetime import date, timedelta

from app.application.services.margin_query_service import MarginQueryService
from app.domain.exceptions import CampaignNotFoundError
from app.domain.repositories.billing_read_repository import BillingReadRepository, MonthCampaignRow, MonthFlightRow
from app.domain.services.carryover import delivery_target
from app.domain.services.monthly_review import review_state
from app.domain.value_objects.billing_report import (
    BillingCampaign,
    BillingFlight,
    BillingFlightState,
    BillingLine,
    BillingReport,
)
from app.domain.value_objects.margin_report import FlightReport


class BillingQueryService:
    """Reads the billing of a month per campaign, line and flight. Writes nothing.

    The billing, billable volume, basis and delivered volume of every flight that has started come from the margin
    read itself, so they are by construction the `revenue`, `billable` and `billing_basis` of `GET /margin`: a closed
    flight's from its snapshot, any other priced by the function the closing uses. The review state is derived as of
    D-1 from the flights and the latest review event, as the review itself derives it.
    """

    def __init__(self, margin: MarginQueryService, reads: BillingReadRepository, today: Callable[[], date]) -> None:
        self._margin = margin
        self._reads = reads
        self._today = today

    def get_billing(self, year: int, month: int, campaign_id: int | None = None) -> BillingReport:
        if campaign_id is not None and not self._reads.campaign_exists(campaign_id):
            raise CampaignNotFoundError(f"campaign {campaign_id} does not exist")
        as_of = self._today() - timedelta(days=1)
        margin = self._margin.get_margin(year, month, campaign_id)
        reports = {
            flight.flight_id: flight
            for campaign in margin.campaigns for line in campaign.lines for flight in line.flights
        }
        flights_by_campaign: dict[int, list[MonthFlightRow]] = defaultdict(list)
        for row in self._reads.month_flights(year, month, campaign_id):
            flights_by_campaign[row.campaign_id].append(row)
        campaigns = tuple(
            self._campaign(row, flights_by_campaign[row.campaign_id], reports)
            for row in self._reads.month_campaigns(year, month, as_of, campaign_id)
        )
        return BillingReport(year=year, month=month, as_of=as_of, campaigns=campaigns)

    def _campaign(
        self, row: MonthCampaignRow, flights: list[MonthFlightRow], reports: dict[int, FlightReport]
    ) -> BillingCampaign:
        by_line: dict[tuple[int, int], list[BillingFlight]] = defaultdict(list)
        for flight in flights:
            by_line[(flight.line_number, flight.campaign_line_id)].append(_flight(flight, reports.get(flight.flight_id)))
        lines = tuple(
            BillingLine(campaign_line_id=line_id, line_number=number, flights=tuple(line_flights))
            for (number, line_id), line_flights in sorted(by_line.items())
        )
        return BillingCampaign(
            campaign_id=row.campaign_id, name=row.name, agency=row.agency, advertiser=row.advertiser,
            review_state=review_state(row.counts, row.latest_kind), review_set_by=row.latest_by,
            review_set_at=row.latest_at, lines=lines,
        )


_STATES = {"running": BillingFlightState.RUNNING, "pending_close": BillingFlightState.PENDING_CLOSE,
           "closed": BillingFlightState.CLOSED}


def _flight(row: MonthFlightRow, report: FlightReport | None) -> BillingFlight:
    """The flight with the margin read's figures; a flight the margin does not list has not started and bills nothing."""
    target = delivery_target(row.contracted_impressions, row.carryover or 0)
    if report is None:
        return BillingFlight(
            flight_id=row.flight_id, flight_start=row.flight_start, flight_end=row.flight_end,
            state=BillingFlightState.NOT_STARTED, delivery_metric=row.delivery_metric,
            contracted_impressions=row.contracted_impressions, carryover=row.carryover,
            carryover_billable=row.carryover_billable, delivery_target=target, delivered=None, billable=None,
            billing=None, billing_basis=None, sale_cpm=row.sale_cpm, adjustment=row.adjustment,
        )
    margin = report.margin
    return BillingFlight(
        flight_id=row.flight_id, flight_start=row.flight_start, flight_end=row.flight_end,
        state=_STATES[report.state.value], delivery_metric=row.delivery_metric,
        contracted_impressions=row.contracted_impressions, carryover=row.carryover,
        carryover_billable=row.carryover_billable, delivery_target=target, delivered=margin.delivered,
        billable=margin.billable, billing=margin.revenue, billing_basis=margin.billing_basis, sale_cpm=row.sale_cpm,
        adjustment=row.adjustment,
    )
