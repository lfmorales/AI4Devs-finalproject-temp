from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import exists, func, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.domain.exceptions import SystemPlatformRateMissingError
from app.domain.repositories.margin_repositories import (
    AppliedRateRepository,
    MarginClosingTransaction,
    MarginFlightRepository,
    PlatformRateRepository,
    RebateScheduleRepository,
)
from app.domain.value_objects.priced_flight import FlightFacts, PlatformRates, PricedFlight
from app.domain.value_objects.rebate import Bracket, CounterKey, RebateSchedule
from app.infrastructure.persistence.models.campaign import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignPeriodRecord,
    CampaignRecord,
)
from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord
from app.infrastructure.persistence.models.margin import (
    AppliedRateBracketRecord,
    AppliedRateRecord,
    PlatformRateSettingRecord,
    RebateBracketRecord,
    RebateScheduleRecord,
)
from app.infrastructure.persistence.models.masters import AgencyRecord, ChannelRecord

# The first key of the advisory locks that serialise the closing of a month; the second is year * 100 + month.
_CLOSING_LOCK_NAMESPACE = 4242


class SqlAlchemyRebateScheduleRepository(RebateScheduleRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_schedules(self) -> list[RebateSchedule]:
        brackets: dict[int, list[Bracket]] = {}
        for bracket in self._session.scalars(
            select(RebateBracketRecord).order_by(RebateBracketRecord.rebate_schedule_id, RebateBracketRecord.position)
        ):
            brackets.setdefault(bracket.rebate_schedule_id, []).append(
                Bracket(bracket.lower, bracket.upper, bracket.rate)
            )
        rows = self._session.execute(
            select(RebateScheduleRecord, ChannelRecord.name)
            .outerjoin(ChannelRecord, ChannelRecord.id == RebateScheduleRecord.channel_id)
            .order_by(RebateScheduleRecord.id)
        ).all()
        return [
            RebateSchedule(
                schedule_id=record.id, group_id=record.holding_group_id, agency_id=record.agency_id,
                channel=channel_name, scope=record.scope, valid_from=record.valid_from, valid_to=record.valid_to,
                brackets=tuple(brackets.get(record.id, ())),
            )
            for record, channel_name in rows
        ]


class SqlAlchemyPlatformRateRepository(PlatformRateRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def current_rates(self) -> PlatformRates:
        system: Decimal | None = None
        by_campaign_type: dict[int, Decimal] = {}
        by_agency: dict[int, Decimal] = {}
        by_line: dict[int, Decimal] = {}
        # Settings are only added, so reading them oldest first and overwriting leaves the latest of each key.
        for setting in self._session.scalars(select(PlatformRateSettingRecord).order_by(PlatformRateSettingRecord.id)):
            if setting.level == "system":
                system = setting.rate_per_thousand
            elif setting.level == "agency" and setting.agency_id is not None:
                by_agency[setting.agency_id] = setting.rate_per_thousand
            elif setting.level == "campaign_type" and setting.campaign_type_id is not None:
                by_campaign_type[setting.campaign_type_id] = setting.rate_per_thousand
            elif setting.level == "line" and setting.campaign_line_id is not None:
                by_line[setting.campaign_line_id] = setting.rate_per_thousand
        if system is None:
            raise SystemPlatformRateMissingError("no system platform rate is stored")
        return PlatformRates(system=system, by_campaign_type=by_campaign_type, by_agency=by_agency, by_line=by_line)


class SqlAlchemyMarginFlightRepository(MarginFlightRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _not_frozen():
        return ~exists().where(AppliedRateRecord.campaign_line_period_id == CampaignLinePeriodRecord.id)

    def open_ended_flights(self, year: int, month: int, as_of: date) -> list[FlightFacts]:
        flight = CampaignLinePeriodRecord
        window = (
            DailyDeliveryRecord.campaign_line_id == flight.campaign_line_id,
            DailyDeliveryRecord.delivery_date.between(flight.flight_start, flight.flight_end),
        )
        # Both aggregates run in the database over the indexed (line, date) pair: no delivery row is fetched.
        delivered = select(func.coalesce(func.sum(DailyDeliveryRecord.impressions), 0)).where(*window).scalar_subquery()
        media_cost = select(func.coalesce(func.sum(DailyDeliveryRecord.media_cost), 0)).where(*window).scalar_subquery()
        rows = self._session.execute(
            select(
                flight.id, CampaignLineRecord.id, CampaignRecord.id, flight.flight_start, flight.flight_end,
                AgencyRecord.holding_group_id, AgencyRecord.id, CampaignRecord.campaign_type_id,
                ChannelRecord.name, ChannelRecord.id, CampaignLineRecord.scope, flight.contracted_impressions,
                CampaignLineRecord.sale_cpm, delivered, media_cost,
            )
            .select_from(flight)
            .join(CampaignLineRecord, CampaignLineRecord.id == flight.campaign_line_id)
            .join(CampaignRecord, CampaignRecord.id == CampaignLineRecord.campaign_id)
            .join(AgencyRecord, AgencyRecord.id == CampaignRecord.agency_id)
            .join(ChannelRecord, ChannelRecord.id == CampaignLineRecord.channel_id)
            .join(CampaignPeriodRecord, CampaignPeriodRecord.id == flight.campaign_period_id)
            .where(
                CampaignPeriodRecord.period_year == year,
                CampaignPeriodRecord.period_month == month,
                flight.flight_end <= as_of,
                self._not_frozen(),
            )
            .order_by(flight.flight_start, flight.id)
        ).all()
        return [
            FlightFacts(
                flight_id=row[0], campaign_line_id=row[1], campaign_id=row[2], flight_start=row[3], flight_end=row[4],
                group_id=row[5], agency_id=row[6], campaign_type_id=row[7], channel=row[8], channel_id=row[9],
                scope=row[10], contracted_impressions=int(row[11]), sale_cpm=row[12],
                delivered_impressions=int(row[13]), media_cost=Decimal(row[14]),
            )
            for row in rows
        ]

    def earliest_month_with_open_flights(self, year: int, before_month: int, as_of: date) -> int | None:
        flight = CampaignLinePeriodRecord
        return self._session.scalar(
            select(func.min(CampaignPeriodRecord.period_month))
            .select_from(flight)
            .join(CampaignPeriodRecord, CampaignPeriodRecord.id == flight.campaign_period_id)
            .where(
                CampaignPeriodRecord.period_year == year,
                CampaignPeriodRecord.period_month < before_month,
                flight.flight_end <= as_of,
                self._not_frozen(),
            )
        )


class SqlAlchemyAppliedRateRepository(AppliedRateRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def opening_positions(self, year: int) -> dict[CounterKey, Decimal]:
        latest = (
            select(
                AppliedRateRecord.counter_group_id, AppliedRateRecord.counter_agency_id, ChannelRecord.name,
                AppliedRateRecord.position_after,
            )
            .join(CampaignLinePeriodRecord, CampaignLinePeriodRecord.id == AppliedRateRecord.campaign_line_period_id)
            .join(ChannelRecord, ChannelRecord.id == AppliedRateRecord.counter_channel_id)
            .where(AppliedRateRecord.counter_year == year)
            .ext(postgresql.distinct_on(
                AppliedRateRecord.counter_group_id, AppliedRateRecord.counter_agency_id,
                AppliedRateRecord.counter_channel_id,
            ))
            .order_by(
                AppliedRateRecord.counter_group_id, AppliedRateRecord.counter_agency_id,
                AppliedRateRecord.counter_channel_id,
                CampaignLinePeriodRecord.flight_start.desc(), CampaignLinePeriodRecord.id.desc(),
            )
        )
        return {
            CounterKey(group_id, agency_id, channel_name, year): position_after
            for group_id, agency_id, channel_name, position_after in self._session.execute(latest)
        }

    def count_frozen(self, year: int, month: int) -> int:
        return int(self._session.scalar(
            select(func.count())
            .select_from(AppliedRateRecord)
            .join(CampaignLinePeriodRecord, CampaignLinePeriodRecord.id == AppliedRateRecord.campaign_line_period_id)
            .join(CampaignPeriodRecord, CampaignPeriodRecord.id == CampaignLinePeriodRecord.campaign_period_id)
            .where(CampaignPeriodRecord.period_year == year, CampaignPeriodRecord.period_month == month)
        ) or 0)

    def save(self, priced: Sequence[PricedFlight], closed_at: datetime, closed_by: int) -> None:
        for item in priced:
            rebate = item.rebate
            row = AppliedRateRecord(
                campaign_line_period_id=item.facts.flight_id,
                rebate_schedule_id=rebate.schedule_id,
                ladder_step=int(rebate.step),
                source_year=rebate.source_year,
                agency_exception=rebate.agency_exception,
                zero_reason=rebate.zero_reason.value if rebate.zero_reason is not None else None,
                effective_rate=rebate.effective_rate,
                counter_group_id=rebate.counter.group_id,
                counter_agency_id=rebate.counter.agency_id,
                counter_channel_id=item.facts.channel_id,
                counter_year=rebate.counter.year,
                position_before=rebate.position_before,
                position_after=rebate.position_after,
                rebate_amount=rebate.rebate,
                platform_rate=item.platform.rate,
                closed_at=closed_at,
                closed_by=closed_by,
            )
            self._session.add(row)
            self._session.flush()
            for position, charge in enumerate(rebate.charges, start=1):
                self._session.add(AppliedRateBracketRecord(
                    applied_rate_id=row.id, position=position, lower=charge.lower, upper=charge.upper,
                    rate=charge.rate, amount=charge.amount, rebate=charge.rebate,
                ))
            self._session.flush()


class SqlAlchemyMarginClosingTransaction(MarginClosingTransaction):
    """One database transaction on the caller's session: closing a month lands whole or not at all."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self.schedules = SqlAlchemyRebateScheduleRepository(session)
        self.platform_rates = SqlAlchemyPlatformRateRepository(session)
        self.flights = SqlAlchemyMarginFlightRepository(session)
        self.applied_rates = SqlAlchemyAppliedRateRepository(session)

    def lock_month(self, year: int, month: int) -> None:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :key)"),
            {"namespace": _CLOSING_LOCK_NAMESPACE, "key": year * 100 + month},
        )

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
