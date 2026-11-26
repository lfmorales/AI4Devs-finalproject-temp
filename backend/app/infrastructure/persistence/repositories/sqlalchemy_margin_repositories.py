import dataclasses
from calendar import monthrange
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Numeric, Row, RowMapping, Select, cast, exists, func, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.exceptions import RebateRuleError, SystemPlatformRateMissingError
from app.domain.repositories.margin_repositories import (
    AppliedRateRepository,
    CampaignMonthStanding,
    MarginClosingTransaction,
    MarginFlightRepository,
    MarginMastersTransaction,
    MarginReadRepository,
    MonthClosingRepository,
    PlatformRateRepository,
    RebateScheduleRepository,
)
from app.domain.services.closed_flight import snapshot_of
from app.domain.services.monthly_review import FlightCounts
from app.domain.value_objects.billing import BillingAdjustment, BillingBasis
from app.domain.value_objects.closed_flight import ClosedFlightSnapshot
from app.domain.value_objects.margin_report import FrozenRates
from app.domain.value_objects.platform_rate import NewPlatformRateSetting, PlatformRateLevel, PlatformRateSetting
from app.domain.value_objects.priced_flight import FlightFacts, PlatformRates, PricedFlight, ReadFlight
from app.domain.value_objects.rebate import Bracket, CounterKey, NewRebateSchedule, RebateSchedule
from app.domain.value_objects.review import ReviewKind
from app.domain.value_objects.volume_commitment import VolumeCommitment
from app.infrastructure.persistence.models.campaign import (
    CampaignLinePeriodRecord,
    CampaignLineRecord,
    CampaignPeriodRecord,
    CampaignRecord,
)
from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord, IngestionBatchRecord
from app.infrastructure.persistence.models.margin import (
    AppliedRateBracketRecord,
    AppliedRateRecord,
    CampaignPeriodReviewRecord,
    ClosedFlightSnapshotRecord,
    FlightBillingAdjustmentRecord,
    MonthClosingBatchRecord,
    MonthClosingRecord,
    PlatformRateSettingRecord,
    RebateBracketRecord,
    RebateScheduleRecord,
)
from app.infrastructure.persistence.models.masters import AgencyRecord, ChannelRecord, DSPRecord
from app.infrastructure.persistence.repositories.delivered_volume import delivered_in_channel_metric

# The first key of the advisory locks that serialise the closing of a month; the second is year * 100 + month.
_CLOSING_LOCK_NAMESPACE = 4242
# Public: the edits of a month (a carry-over, an adjustment, a review) take the same lock as its closing.
CLOSING_LOCK_NAMESPACE = _CLOSING_LOCK_NAMESPACE


_EXCLUSION_VIOLATION = "23P01"
_FOREIGN_KEY_VIOLATION = "23503"


def _translate_integrity_error(error: IntegrityError) -> RebateRuleError:
    """The database's refusals that a client can cause, as rules of the domain."""
    sqlstate = getattr(error.orig, "sqlstate", None)
    if sqlstate == _EXCLUSION_VIOLATION:
        return RebateRuleError("schedule_overlaps_existing", "another schedule of the same key overlaps this validity")
    if sqlstate == _FOREIGN_KEY_VIOLATION:
        return RebateRuleError("reference_not_found", "a referenced group, agency, channel, line or campaign type is missing")
    raise error


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


    def add_schedule(self, new: NewRebateSchedule) -> int:
        record = RebateScheduleRecord(
            holding_group_id=new.holding_group_id, agency_id=new.agency_id, channel_id=new.channel_id,
            scope=new.scope, valid_from=new.valid_from, valid_to=new.valid_to,
        )
        try:
            self._session.add(record)
            self._session.flush()
            for position, bracket in enumerate(new.brackets, start=1):
                self._session.add(RebateBracketRecord(
                    rebate_schedule_id=record.id, position=position, lower=bracket.lower, upper=bracket.upper,
                    rate=bracket.rate,
                ))
            self._session.flush()
        except IntegrityError as error:
            raise _translate_integrity_error(error) from None
        return record.id


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


    def add_setting(self, new: NewPlatformRateSetting) -> PlatformRateSetting:
        record = PlatformRateSettingRecord(
            level=new.level.value, rate_per_thousand=new.rate_per_thousand, created_by=new.created_by,
            campaign_line_id=new.campaign_line_id, agency_id=new.agency_id, campaign_type_id=new.campaign_type_id,
        )
        try:
            self._session.add(record)
            self._session.flush()
            self._session.refresh(record)
        except IntegrityError as error:
            raise _translate_integrity_error(error) from None
        return PlatformRateSetting(
            setting_id=record.id, level=PlatformRateLevel(record.level), rate_per_thousand=record.rate_per_thousand,
            created_by=record.created_by, created_at=record.created_at, campaign_line_id=record.campaign_line_id,
            agency_id=record.agency_id, campaign_type_id=record.campaign_type_id,
        )


def _flight_facts_query(
    *extra: ColumnElement[Any], metric: ColumnElement[str] | None = None
) -> Select[*tuple[Any, ...]]:
    """Every flight with the facts its margin is computed from, joined to its line, campaign, agency, channel and period.

    The one query behind the closing (`open_ended_flights`) and the reads (`list_flights`): each adds its own filters,
    order and `extra` columns. The delivery is summed in the database over the indexed (line, date) pair, inside the
    flight's own window: no delivery row is fetched. The delivery metric is the channel's, unless `metric` gives
    another, which the delivered volume is then summed in.
    """
    unit = ChannelRecord.delivery_metric if metric is None else metric
    flight = CampaignLinePeriodRecord
    window = (
        DailyDeliveryRecord.campaign_line_id == flight.campaign_line_id,
        DailyDeliveryRecord.delivery_date.between(flight.flight_start, flight.flight_end),
    )
    delivered_impressions = (
        select(func.coalesce(func.sum(DailyDeliveryRecord.impressions), 0)).where(*window).scalar_subquery()
    )
    # The delivery in the channel's own unit, as a four-decimal number (OTS has decimals, impressions do not).
    delivered = select(
        cast(func.coalesce(func.sum(delivered_in_channel_metric(metric)), 0), Numeric(18, 4))
    ).where(*window).scalar_subquery()
    media_cost = select(func.coalesce(func.sum(DailyDeliveryRecord.media_cost), 0)).where(*window).scalar_subquery()
    # What the DSP reported besides its cost: the revenue a target flight earns, the buyer's spend its gross is
    # compared with, and the two data costs as one amount, whose presence is flagged.
    reported_revenue = (
        select(func.coalesce(func.sum(DailyDeliveryRecord.reported_revenue), 0)).where(*window).scalar_subquery()
    )
    buyer_spend = select(func.coalesce(func.sum(DailyDeliveryRecord.buyer_spend), 0)).where(*window).scalar_subquery()
    data_cost = select(
        func.coalesce(func.sum(DailyDeliveryRecord.third_party_data_cost + DailyDeliveryRecord.audience_data_cost), 0)
    ).where(*window).scalar_subquery()
    # The adjustment in force is the latest row of the flight, by id (the table is append-only). Its id, basis and amount
    # are read by correlated subqueries ordered by id, over the (flight, id) index.
    latest = (
        select(FlightBillingAdjustmentRecord.id, FlightBillingAdjustmentRecord.basis, FlightBillingAdjustmentRecord.amount)
        .where(FlightBillingAdjustmentRecord.campaign_line_period_id == flight.id)
        .order_by(FlightBillingAdjustmentRecord.id.desc())
        .limit(1)
    )
    adjustment_basis = latest.with_only_columns(FlightBillingAdjustmentRecord.basis).scalar_subquery()
    adjustment_amount = latest.with_only_columns(FlightBillingAdjustmentRecord.amount).scalar_subquery()
    adjustment_id = latest.with_only_columns(FlightBillingAdjustmentRecord.id).scalar_subquery()
    return (
        select(
            flight.id.label("flight_id"),
            CampaignLineRecord.id.label("campaign_line_id"),
            CampaignRecord.id.label("campaign_id"),
            flight.flight_start.label("flight_start"),
            flight.flight_end.label("flight_end"),
            AgencyRecord.holding_group_id.label("group_id"),
            AgencyRecord.id.label("agency_id"),
            CampaignRecord.campaign_type_id.label("campaign_type_id"),
            ChannelRecord.name.label("channel"),
            ChannelRecord.id.label("channel_id"),
            CampaignLineRecord.scope.label("scope"),
            flight.contracted_impressions.label("contracted_impressions"),
            CampaignLineRecord.sale_cpm.label("sale_cpm"),
            delivered_impressions.label("delivered_impressions"),
            media_cost.label("media_cost"),
            unit.label("delivery_metric"),
            delivered.label("delivered"),
            CampaignLineRecord.volume_commitment.label("volume_commitment"),
            reported_revenue.label("reported_revenue"),
            buyer_spend.label("buyer_spend"),
            data_cost.label("data_cost"),
            flight.carryover.label("carryover"),
            flight.carryover_billable.label("carryover_billable"),
            adjustment_basis.label("adjustment_basis"),
            adjustment_amount.label("adjustment_amount"),
            adjustment_id.label("adjustment_id"),
            *extra,
        )
        .select_from(flight)
        .join(CampaignLineRecord, CampaignLineRecord.id == flight.campaign_line_id)
        .join(CampaignRecord, CampaignRecord.id == CampaignLineRecord.campaign_id)
        .join(AgencyRecord, AgencyRecord.id == CampaignRecord.agency_id)
        .join(ChannelRecord, ChannelRecord.id == CampaignLineRecord.channel_id)
        .join(CampaignPeriodRecord, CampaignPeriodRecord.id == flight.campaign_period_id)
    )


# Public: the adjustments of a flight price it with the very facts the closing and the reads use.
flight_facts_query = _flight_facts_query


def _flight_facts(row: Row[Any]) -> FlightFacts:
    values = row._mapping
    return FlightFacts(
        flight_id=values["flight_id"], campaign_line_id=values["campaign_line_id"], campaign_id=values["campaign_id"],
        flight_start=values["flight_start"], flight_end=values["flight_end"], group_id=values["group_id"],
        agency_id=values["agency_id"], campaign_type_id=values["campaign_type_id"], channel=values["channel"],
        channel_id=values["channel_id"], scope=values["scope"],
        contracted_impressions=int(values["contracted_impressions"]), sale_cpm=values["sale_cpm"],
        delivered_impressions=int(values["delivered_impressions"]), media_cost=Decimal(values["media_cost"]),
        delivery_metric=values["delivery_metric"], delivered=Decimal(values["delivered"]),
        volume_commitment=VolumeCommitment(values["volume_commitment"]),
        reported_revenue=Decimal(values["reported_revenue"]), buyer_spend=Decimal(values["buyer_spend"]),
        data_cost=Decimal(values["data_cost"]),
        carryover=int(values["carryover"]), carryover_billable=bool(values["carryover_billable"]),
        adjustment=(
            None if values["adjustment_basis"] is None
            else BillingAdjustment(BillingBasis(values["adjustment_basis"]), values["adjustment_amount"])
        ),
        adjustment_id=values["adjustment_id"],
    )


class SqlAlchemyMarginFlightRepository(MarginFlightRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _not_frozen() -> ColumnElement[bool]:
        return ~exists().where(AppliedRateRecord.campaign_line_period_id == CampaignLinePeriodRecord.id)

    def open_ended_flights(self, year: int, month: int, as_of: date) -> list[FlightFacts]:
        flight = CampaignLinePeriodRecord
        rows = self._session.execute(
            _flight_facts_query()
            .where(
                CampaignPeriodRecord.period_year == year,
                CampaignPeriodRecord.period_month == month,
                flight.flight_end <= as_of,
                self._not_frozen(),
            )
            .order_by(flight.flight_start, flight.id)
        ).all()
        return [_flight_facts(row) for row in rows]

    def dsps_without_the_months_last_day(self, year: int, month: int, as_of: date) -> list[str]:
        flight = CampaignLinePeriodRecord
        last_day = date(year, month, monthrange(year, month)[1])
        loaded = exists().where(
            IngestionBatchRecord.dsp_id == CampaignLineRecord.dsp_id,
            IngestionBatchRecord.status == "succeeded",
            IngestionBatchRecord.window_start <= last_day,
            IngestionBatchRecord.window_end >= last_day,
        )
        return list(self._session.scalars(
            select(DSPRecord.name)
            .select_from(flight)
            .join(CampaignLineRecord, CampaignLineRecord.id == flight.campaign_line_id)
            .join(DSPRecord, DSPRecord.id == CampaignLineRecord.dsp_id)
            .join(CampaignPeriodRecord, CampaignPeriodRecord.id == flight.campaign_period_id)
            .where(
                CampaignPeriodRecord.period_year == year,
                CampaignPeriodRecord.period_month == month,
                flight.flight_end <= as_of,
                self._not_frozen(),
                ~loaded,
            )
            .distinct()
            .order_by(DSPRecord.name)
        ))

    def campaigns_of_the_month(self, year: int, month: int, as_of: date) -> list[CampaignMonthStanding]:
        flight = CampaignLinePeriodRecord
        frozen = exists().where(AppliedRateRecord.campaign_line_period_id == flight.id)
        latest_kind = (
            select(CampaignPeriodReviewRecord.kind)
            .where(CampaignPeriodReviewRecord.campaign_period_id == CampaignPeriodRecord.id)
            .order_by(CampaignPeriodReviewRecord.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        rows = self._session.execute(
            select(
                CampaignRecord.id,
                CampaignRecord.name,
                func.count(),
                func.count().filter(flight.flight_end <= as_of),
                func.count().filter(frozen),
                latest_kind,
            )
            .select_from(flight)
            .join(CampaignPeriodRecord, CampaignPeriodRecord.id == flight.campaign_period_id)
            .join(CampaignRecord, CampaignRecord.id == CampaignPeriodRecord.campaign_id)
            .where(CampaignPeriodRecord.period_year == year, CampaignPeriodRecord.period_month == month)
            .group_by(CampaignRecord.id, CampaignRecord.name, CampaignPeriodRecord.id)
            .order_by(CampaignRecord.name, CampaignRecord.id)
        ).all()
        return [
            CampaignMonthStanding(
                campaign_id=campaign_id, campaign_name=name,
                counts=FlightCounts(total=int(total), ended=int(ended), frozen=int(frozen_count)),
                latest_event=None if kind is None else ReviewKind(kind),
            )
            for campaign_id, name, total, ended, frozen_count, kind in rows
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


_SNAPSHOT_FIELDS = tuple(field.name for field in dataclasses.fields(ClosedFlightSnapshot))


def _snapshot(values: RowMapping) -> ClosedFlightSnapshot:
    """The snapshot of a frozen flight as stored, column for field."""
    stored = {name: values[f"snapshot_{name}"] for name in _SNAPSHOT_FIELDS}
    stored["volume_commitment"] = VolumeCommitment(stored["volume_commitment"])
    if stored["billing_basis"] is not None:
        stored["billing_basis"] = BillingBasis(stored["billing_basis"])
    return ClosedFlightSnapshot(**stored)


class SqlAlchemyMarginReadRepository(MarginReadRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def campaign_exists(self, campaign_id: int) -> bool:
        return bool(self._session.scalar(select(exists().where(CampaignRecord.id == campaign_id))))

    def list_flights(
        self,
        as_of: date,
        year: int | None = None,
        month: int | None = None,
        campaign_id: int | None = None,
        unfrozen_only: bool = False,
    ) -> list[ReadFlight]:
        flight = CampaignLinePeriodRecord
        applied = AppliedRateRecord
        snapshot = ClosedFlightSnapshotRecord
        query = (
            _flight_facts_query(
                CampaignRecord.name.label("campaign_name"),
                CampaignRecord.status.label("campaign_status"),
                CampaignLineRecord.line_number.label("line_number"),
                CampaignPeriodRecord.period_year.label("period_year"),
                CampaignPeriodRecord.period_month.label("period_month"),
                applied.id.label("applied_id"),
                applied.rebate_amount.label("rebate_amount"),
                applied.platform_rate.label("platform_rate"),
                applied.effective_rate.label("effective_rate"),
                applied.ladder_step.label("ladder_step"),
                applied.agency_exception.label("agency_exception"),
                applied.zero_reason.label("zero_reason"),
                applied.source_year.label("source_year"),
                applied.position_before.label("position_before"),
                applied.position_after.label("position_after"),
                applied.revenue_amount.label("frozen_revenue_amount"),
                applied.rebate_base_amount.label("frozen_rebate_base_amount"),
                *(getattr(snapshot, name).label(f"snapshot_{name}") for name in _SNAPSHOT_FIELDS),
                # A closed flight's current delivery is summed in the metric it was closed in, whatever its channel
                # counts in now, so that the check never compares OTS with impressions.
                metric=func.coalesce(snapshot.delivery_metric, ChannelRecord.delivery_metric),
            )
            .outerjoin(applied, applied.campaign_line_period_id == flight.id)
            .outerjoin(snapshot, snapshot.applied_rate_id == applied.id)
            .where(flight.flight_start <= as_of)
            .order_by(flight.flight_start, flight.id)
        )
        if year is not None:
            query = query.where(func.extract("year", flight.flight_start) == year)
        if month is not None:
            query = query.where(func.extract("month", flight.flight_start) == month)
        if campaign_id is not None:
            query = query.where(CampaignRecord.id == campaign_id)
        if unfrozen_only:
            query = query.where(applied.id.is_(None))
        results: list[ReadFlight] = []
        for row in self._session.execute(query).all():
            values = row._mapping
            frozen = None if values["applied_id"] is None else FrozenRates(
                rebate_amount=values["rebate_amount"], platform_rate=values["platform_rate"],
                effective_rate=values["effective_rate"], ladder_step=int(values["ladder_step"]),
                agency_exception=values["agency_exception"], zero_reason=values["zero_reason"],
                source_year=values["source_year"], position_before=values["position_before"],
                position_after=values["position_after"], revenue_amount=values["frozen_revenue_amount"],
                rebate_base_amount=values["frozen_rebate_base_amount"], snapshot=_snapshot(values),
            )
            results.append(ReadFlight(
                _flight_facts(row), values["campaign_name"], values["campaign_status"], values["line_number"],
                values["period_year"], values["period_month"], frozen,
            ))
        return results


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

    def save(
        self, priced: Sequence[PricedFlight], closed_at: datetime, closed_by: int, month_closing_id: int
    ) -> None:
        for item in priced:
            rebate = item.rebate
            # The revenue and the rebate base as of closing, frozen with the rates: a target flight's reported revenue
            # and gross, and a committed flight's billing, which is both.
            target = item.facts.volume_commitment is VolumeCommitment.TARGET
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
                revenue_amount=item.margin.revenue,
                rebate_base_amount=item.margin.gross_revenue if target else item.margin.revenue,
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
            self._session.add(_snapshot_record(item, row.id, month_closing_id))
            self._session.flush()


def _snapshot_record(item: PricedFlight, applied_rate_id: int, month_closing_id: int) -> ClosedFlightSnapshotRecord:
    """The snapshot the domain builds from the priced flight, column for field: nothing is computed here."""
    snapshot = snapshot_of(item)
    return ClosedFlightSnapshotRecord(
        applied_rate_id=applied_rate_id,
        month_closing_id=month_closing_id,
        revenue=snapshot.revenue,
        contracted_revenue=snapshot.contracted_revenue,
        media_cost=snapshot.media_cost,
        rebate=snapshot.rebate,
        platform_cost=snapshot.platform_cost,
        margin=snapshot.margin,
        gross_revenue=snapshot.gross_revenue,
        delivered_impressions=snapshot.delivered_impressions,
        delivered=snapshot.delivered,
        window_media_cost=snapshot.window_media_cost,
        window_reported_revenue=snapshot.window_reported_revenue,
        window_buyer_spend=snapshot.window_buyer_spend,
        window_data_cost=snapshot.window_data_cost,
        gross_differs_from_buyer_spend=snapshot.gross_differs_from_buyer_spend,
        data_cost_reported=snapshot.data_cost_reported,
        delivery_metric=snapshot.delivery_metric,
        sale_cpm=snapshot.sale_cpm,
        contracted_impressions=snapshot.contracted_impressions,
        volume_commitment=snapshot.volume_commitment.value,
        billing_basis=None if snapshot.billing_basis is None else snapshot.billing_basis.value,
        billable=snapshot.billable,
        carryover=snapshot.carryover,
        carryover_billable=snapshot.carryover_billable,
        billing_adjustment_id=snapshot.billing_adjustment_id,
    )


class SqlAlchemyMonthClosingRepository(MonthClosingRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_closing(
        self, year: int, month: int, closed_at: datetime, closed_by: int, as_of: date, flight_ids: Sequence[int]
    ) -> int:
        header = MonthClosingRecord(
            period_year=year, period_month=month, closed_at=closed_at, closed_by=closed_by, as_of=as_of
        )
        self._session.add(header)
        self._session.flush()
        dsps_of_the_flights = (
            select(CampaignLineRecord.dsp_id)
            .join(CampaignLinePeriodRecord, CampaignLinePeriodRecord.campaign_line_id == CampaignLineRecord.id)
            .where(CampaignLinePeriodRecord.id.in_(list(flight_ids)))
        )
        latest_succeeded = (
            select(IngestionBatchRecord.dsp_id, IngestionBatchRecord.id)
            .where(
                IngestionBatchRecord.status == "succeeded",
                IngestionBatchRecord.dsp_id.in_(dsps_of_the_flights),
            )
            .ext(postgresql.distinct_on(IngestionBatchRecord.dsp_id))
            .order_by(
                IngestionBatchRecord.dsp_id,
                IngestionBatchRecord.finished_at.desc().nulls_last(),
                IngestionBatchRecord.id.desc(),
            )
        )
        for dsp_id, batch_id in self._session.execute(latest_succeeded):
            self._session.add(MonthClosingBatchRecord(
                month_closing_id=header.id, dsp_id=dsp_id, ingestion_batch_id=batch_id,
            ))
        self._session.flush()
        return header.id

    def count_closings(self, year: int, month: int) -> int:
        return int(self._session.scalar(
            select(func.count())
            .select_from(MonthClosingRecord)
            .where(MonthClosingRecord.period_year == year, MonthClosingRecord.period_month == month)
        ) or 0)


class SqlAlchemyMarginClosingTransaction(MarginClosingTransaction):
    """One database transaction on the caller's session: closing a month lands whole or not at all."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self.schedules = SqlAlchemyRebateScheduleRepository(session)
        self.platform_rates = SqlAlchemyPlatformRateRepository(session)
        self.flights = SqlAlchemyMarginFlightRepository(session)
        self.applied_rates = SqlAlchemyAppliedRateRepository(session)
        self.closings = SqlAlchemyMonthClosingRepository(session)

    def lock_month(self, year: int, month: int) -> None:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :key)"),
            {"namespace": _CLOSING_LOCK_NAMESPACE, "key": year * 100 + month},
        )

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


class SqlAlchemyMarginMastersTransaction(MarginMastersTransaction):
    """One database transaction on the caller's session for creating schedules and platform rates."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self.schedules = SqlAlchemyRebateScheduleRepository(session)
        self.platform_rates = SqlAlchemyPlatformRateRepository(session)

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
