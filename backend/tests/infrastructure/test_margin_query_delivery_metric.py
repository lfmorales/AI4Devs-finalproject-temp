"""The margin read counts each flight in its channel's metric and nulls the totals that would add two metrics."""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.application.services.margin_query_service import MarginQueryService
from app.domain.value_objects.margin_report import MarginReport
from app.infrastructure.persistence.repositories.sqlalchemy_margin_repositories import (
    SqlAlchemyAppliedRateRepository,
    SqlAlchemyMarginReadRepository,
    SqlAlchemyPlatformRateRepository,
    SqlAlchemyRebateScheduleRepository,
)
from tests.fixtures.delivery_data import insert_campaign_line, insert_delivery, insert_ingestion_batch

TODAY = date(2026, 9, 5)


def _report(session: Session) -> MarginReport:
    service = MarginQueryService(
        flights=SqlAlchemyMarginReadRepository(session),
        schedules=SqlAlchemyRebateScheduleRepository(session),
        platform_rates=SqlAlchemyPlatformRateRepository(session),
        applied_rates=SqlAlchemyAppliedRateRepository(session),
        today=lambda: TODAY,
    )
    return service.get_margin()


def _campaign(session: Session, name: str, metric: str, impressions: int, ots: str = "0") -> None:
    line_id = insert_campaign_line(session, campaign_name=name, delivery_metric=metric)
    insert_delivery(
        session, line_id, date(2026, 8, 10), impressions, insert_ingestion_batch(session), ots=Decimal(ots),
    )


def test_the_grand_total_of_a_dooh_and_a_ctv_campaign_has_no_metric_but_sums_impressions_and_amounts(
    rolled_back_session: Session,
) -> None:
    _campaign(rolled_back_session, "Dooh", "ots", 12_000, "280000.5000")
    _campaign(rolled_back_session, "Ctv", "impressions", 198_800)

    report = _report(rolled_back_session)

    totals = report.totals
    assert totals.delivery_metric is None and totals.contracted_impressions is None and totals.delivered is None
    assert totals.delivered_impressions == 210_800
    assert totals.revenue == sum((campaign.totals.revenue for campaign in report.campaigns), Decimal("0.00"))
    assert totals.platform_cost == Decimal("210.80")
    by_name = {campaign.name: campaign for campaign in report.campaigns}
    assert by_name["Dooh"].totals.delivery_metric == "ots"
    assert by_name["Dooh"].totals.delivered == Decimal("280000.5000")
    assert by_name["Ctv"].totals.delivery_metric == "impressions"


def test_the_grand_total_of_impressions_campaigns_is_summed_with_the_metric_impressions(
    rolled_back_session: Session,
) -> None:
    _campaign(rolled_back_session, "First", "impressions", 1_000)
    _campaign(rolled_back_session, "Second", "impressions", 250)

    totals = _report(rolled_back_session).totals

    assert totals.delivery_metric == "impressions"
    assert totals.delivered == Decimal(1_250) and totals.delivered_impressions == 1_250
    assert totals.contracted_impressions == 2_000_000


def test_the_grand_total_of_dooh_campaigns_only_keeps_ots(rolled_back_session: Session) -> None:
    _campaign(rolled_back_session, "First", "ots", 10, "100.5000")
    _campaign(rolled_back_session, "Second", "ots", 20, "0.2500")

    totals = _report(rolled_back_session).totals

    assert (totals.delivery_metric, totals.delivered) == ("ots", Decimal("100.7500"))
