from collections import defaultdict
from collections.abc import Callable
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from app.domain.exceptions import CampaignNotFoundError
from app.domain.repositories.margin_repositories import (
    AppliedRateRepository,
    MarginReadRepository,
    PlatformRateRepository,
    RebateScheduleRepository,
)
from app.domain.services.flight_margin import calculate_flight_margin
from app.domain.services.margin_totals import total_flights, total_lines
from app.domain.services.priced_flights import price_flights
from app.domain.value_objects.margin import FlightEconomics, FlightMargin, FlightStatus
from app.domain.value_objects.margin_report import (
    AppliedRates,
    CampaignReport,
    FlightReport,
    FlightState,
    FrozenRates,
    LineReport,
    MarginReport,
)
from app.domain.value_objects.priced_flight import PricedFlight, ReadFlight
from app.domain.value_objects.rebate import CounterKey


class MarginQueryService:
    """Reads the margin per campaign, line and flight. Writes nothing.

    A closed flight is read from the rates frozen for it. Every other flight that has started is priced by the
    same domain function the closing uses, from the same opening positions, so what it shows is what closing
    the month will freeze.
    """

    def __init__(
        self,
        flights: MarginReadRepository,
        schedules: RebateScheduleRepository,
        platform_rates: PlatformRateRepository,
        applied_rates: AppliedRateRepository,
        today: Callable[[], date],
    ) -> None:
        self._flights = flights
        self._schedules = schedules
        self._platform_rates = platform_rates
        self._applied_rates = applied_rates
        self._today = today

    def get_margin(
        self, year: int | None = None, month: int | None = None, campaign_id: int | None = None
    ) -> MarginReport:
        if campaign_id is not None and not self._flights.campaign_exists(campaign_id):
            raise CampaignNotFoundError(f"campaign {campaign_id} does not exist")
        as_of = self._today() - timedelta(days=1)
        requested = self._flights.list_flights(as_of, year, month, campaign_id)
        priced = self._price_unfrozen(requested, as_of)

        reports = [self._report(flight, priced.get(flight.facts.flight_id), as_of) for flight in requested]
        return self._assemble(requested, reports, as_of)

    def _price_unfrozen(self, requested: list[ReadFlight], as_of: date) -> dict[int, PricedFlight]:
        """Price the unfrozen flights of every year involved together, whatever the filters: a flight's rebate
        depends on the flights of its counter that come before it, which a filter must not hide."""
        years = sorted({flight.facts.flight_start.year for flight in requested if flight.frozen is None})
        if not years:
            return {}
        schedules = self._schedules.list_schedules()
        platform_rates = self._platform_rates.current_rates()
        priced: dict[int, PricedFlight] = {}
        for flight_year in years:
            unfrozen = [f.facts for f in self._flights.list_flights(as_of, year=flight_year, unfrozen_only=True)]
            opening = self._applied_rates.opening_positions(flight_year)
            for item in price_flights(schedules, platform_rates, unfrozen, as_of, opening):
                priced[item.facts.flight_id] = item
        return priced

    @staticmethod
    def _report(flight: ReadFlight, priced: PricedFlight | None, as_of: date) -> FlightReport:
        facts = flight.facts
        if flight.frozen is not None:
            margin = _margin_from_frozen(flight, flight.frozen, as_of)
            return FlightReport(
                facts.flight_id, flight.period_year, flight.period_month, facts.flight_start, facts.flight_end,
                FlightState.CLOSED, margin,
                AppliedRates(
                    flight.frozen.platform_rate, flight.frozen.effective_rate, flight.frozen.ladder_step,
                    flight.frozen.agency_exception, flight.frozen.zero_reason, flight.frozen.source_year,
                ),
            )
        assert priced is not None
        state = FlightState.PENDING_CLOSE if priced.margin.status is FlightStatus.CLOSED else FlightState.RUNNING
        # Until the month is closed the rates can still change, so the figure is provisional.
        margin = replace(priced.margin, provisional=True)
        rebate = priced.rebate
        return FlightReport(
            facts.flight_id, flight.period_year, flight.period_month, facts.flight_start, facts.flight_end,
            state, margin,
            AppliedRates(
                priced.platform.rate, rebate.effective_rate, int(rebate.step), rebate.agency_exception,
                rebate.zero_reason.value if rebate.zero_reason is not None else None, rebate.source_year,
            ),
        )

    @staticmethod
    def _assemble(requested: list[ReadFlight], reports: list[FlightReport], as_of: date) -> MarginReport:
        by_line: dict[int, list[tuple[ReadFlight, FlightReport]]] = defaultdict(list)
        for flight, report in zip(requested, reports):
            by_line[flight.facts.campaign_line_id].append((flight, report))
        lines_by_campaign: dict[int, list[LineReport]] = defaultdict(list)
        campaign_info: dict[int, tuple[str, str, int]] = {}
        for entries in by_line.values():
            first = entries[0][0]
            facts = first.facts
            campaign_info[facts.campaign_id] = (first.campaign_name, first.campaign_status, facts.agency_id)
            flight_reports = tuple(report for _, report in entries)
            lines_by_campaign[facts.campaign_id].append(LineReport(
                campaign_line_id=facts.campaign_line_id, line_number=first.line_number, channel=facts.channel,
                scope=facts.scope, flights=flight_reports,
                totals=total_flights(report.margin for report in flight_reports),
            ))
        campaigns = []
        for campaign_id, lines in lines_by_campaign.items():
            name, status, agency_id = campaign_info[campaign_id]
            ordered = tuple(sorted(lines, key=lambda line: line.line_number))
            campaigns.append(CampaignReport(
                campaign_id=campaign_id, name=name, status=status, agency_id=agency_id, lines=ordered,
                totals=total_lines(line.totals for line in ordered),
            ))
        ordered_campaigns = tuple(sorted(campaigns, key=lambda campaign: (campaign.name, campaign.campaign_id)))
        return MarginReport(as_of, ordered_campaigns, total_lines(campaign.totals for campaign in ordered_campaigns))


def _margin_from_frozen(flight: ReadFlight, frozen: FrozenRates, as_of: date) -> FlightMargin:
    facts = flight.facts
    return calculate_flight_margin(
        FlightEconomics(
            flight_start=facts.flight_start, flight_end=facts.flight_end,
            contracted_impressions=facts.contracted_impressions, sale_cpm=facts.sale_cpm,
            delivered_impressions=facts.delivered_impressions, media_cost=facts.media_cost,
            rebate_amount=frozen.rebate_amount, platform_rate=Decimal(frozen.platform_rate),
        ),
        as_of,
    )
