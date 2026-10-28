"""The private in-progress-month sheet and the domain pricing of its rows.

The file lives in tests/private/, ignored by git: it is read with the csv module and never copied. Every figure of
the comparison comes from the sheet's own columns; none is written in the tests.

How a row is built: one line with one flight of `days_oc` days from the first of October 2026, in its own holding
group, and `as_of` set to the start plus `days_served` minus one, so that the contract days elapsed are the days the
sheet says were served. A row whose `days_served` equals `days_oc` is a closed flight; one with fewer is running.
"""

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from app.domain.services.priced_flights import price_flights
from app.domain.value_objects.priced_flight import FlightFacts, PlatformRates, PricedFlight
from app.domain.value_objects.rebate import Bracket, RebateSchedule

SHEET_PATH = Path(__file__).resolve().parents[1] / "private" / "mes_en_curso.csv"
SKIP_REASON = f"the private sheet {SHEET_PATH.name} is not present in tests/private/ (it is ignored by git)"

MONTH_START = date(2026, 10, 1)

# Rows with no contracted volume (pixels with no purchase cost included) are not part of this cut.
NO_VOLUME_REASON = "sin volumen contratado: no contemplada en este corte"
# Campaign 38 carries a manual adjustment in the source sheet: 37.50 EUR less rebate than its own rate gives.
MANUAL_ADJUSTMENT_ROW = "Campaign 38"
MANUAL_ADJUSTMENT_REASON = "ajuste manual en la hoja de origen: 37,50 € menos de extraprima que su propia tasa"

_DASH_VALUES = {"-", "'-'", '"-"'}


@dataclass(frozen=True)
class SheetRow:
    number: int
    campaign: str
    served_impressions: int
    purchase_cost: Decimal
    rebate_rate: Decimal | None  # None: the sheet has "-", a campaign without a rebate schedule
    rebate_cost: Decimal  # the sheet's rebate on the sale of the whole month, not the accrued one
    platform_cost: Decimal
    oc_impressions: Decimal
    oc_cpm: Decimal | None
    sale: Decimal | None
    total_cost: Decimal
    margin_pct_actual: Decimal | None  # a fraction, 0.2096 for 20.96 %; None where the sheet has "-"
    days_served: int | None
    days_oc: int | None

    @property
    def contracted_impressions(self) -> int:
        """The domain takes whole impressions: the volume is rounded to the nearest one, half up."""
        return int(self.oc_impressions.quantize(Decimal(1), rounding=ROUND_HALF_UP))

    @property
    def fraction(self) -> Decimal:
        """The share of the month accrued: days served over the days of the purchase order."""
        assert self.days_served is not None and self.days_oc
        return Decimal(self.days_served) / Decimal(self.days_oc)

    @property
    def is_closed(self) -> bool:
        return self.days_served == self.days_oc

    @property
    def accrued_revenue(self) -> Decimal:
        assert self.sale is not None
        return self.sale * self.fraction

    @property
    def accrued_rebate(self) -> Decimal:
        return (self.rebate_rate or Decimal(0)) * self.accrued_revenue

    @property
    def expected_margin(self) -> Decimal:
        return self.accrued_revenue - self.purchase_cost - self.accrued_rebate - self.platform_cost

    @property
    def platform_rate(self) -> Decimal:
        """The sheet gives the platform cost, not the rate: the rate it implies for the impressions served."""
        return self.platform_cost / (Decimal(self.served_impressions) / Decimal(1000))

    @property
    def as_of(self) -> date:
        assert self.days_served is not None
        return MONTH_START + timedelta(days=self.days_served - 1)

    @property
    def flight_end(self) -> date:
        assert self.days_oc is not None
        return MONTH_START + timedelta(days=self.days_oc - 1)


def _optional(text: str) -> str | None:
    text = text.strip()
    return None if text in _DASH_VALUES else text


def load_rows(path: Path = SHEET_PATH) -> list[SheetRow]:
    rows: list[SheetRow] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for number, raw in enumerate(csv.DictReader(handle), start=1):
            rebate, cpm, sale = _optional(raw["rebate_rate"]), _optional(raw["oc_cpm"]), _optional(raw["sale"])
            pct, served, oc_days = _optional(raw["margin_pct_actual"]), _optional(raw["days_served"]), _optional(raw["days_oc"])
            rows.append(SheetRow(
                number=number,
                campaign=raw["campaign"],
                served_impressions=int(Decimal(raw["served_impressions"])),
                purchase_cost=Decimal(raw["purchase_cost"]),
                rebate_rate=None if rebate is None else Decimal(rebate),
                rebate_cost=Decimal(raw["rebate_cost"]),
                platform_cost=Decimal(raw["platform_cost"]),
                oc_impressions=Decimal(raw["oc_impressions"]),
                oc_cpm=None if cpm is None else Decimal(cpm),
                sale=None if sale is None else Decimal(sale),
                total_cost=Decimal(raw["total_cost"]),
                margin_pct_actual=None if pct is None else Decimal(pct),
                days_served=None if served is None else int(served),
                days_oc=None if oc_days is None else int(oc_days),
            ))
    return rows


def split_rows(rows: list[SheetRow]) -> tuple[list[SheetRow], list[SheetRow], list[SheetRow]]:
    """The rows compared, the rows with no contracted volume, and the row with a manual adjustment."""
    no_volume = [row for row in rows if row.oc_impressions == 0]
    adjusted = [row for row in rows if row.campaign == MANUAL_ADJUSTMENT_ROW and row.oc_impressions > 0]
    compared = [row for row in rows if row.oc_impressions > 0 and row.campaign != MANUAL_ADJUSTMENT_ROW]
    return compared, no_volume, adjusted


def facts_of(row: SheetRow, flight_start: date = MONTH_START) -> FlightFacts:
    assert row.oc_cpm is not None and row.days_oc is not None
    return FlightFacts(
        flight_id=row.number, campaign_line_id=row.number, campaign_id=row.number,
        flight_start=flight_start, flight_end=flight_start + timedelta(days=row.days_oc - 1),
        group_id=row.number, agency_id=row.number, campaign_type_id=1, channel="Directo", channel_id=1,
        scope="national", contracted_impressions=row.contracted_impressions, sale_cpm=row.oc_cpm,
        delivered_impressions=row.served_impressions, media_cost=row.purchase_cost,
    )


def schedule_of(row: SheetRow) -> RebateSchedule | None:
    if row.rebate_rate is None:
        return None
    return RebateSchedule(
        schedule_id=row.number, group_id=row.number, agency_id=None, channel=None, scope=None,
        valid_from=date(2026, 1, 1), valid_to=None, brackets=(Bracket(Decimal(0), None, row.rebate_rate),),
    )


def price_row(row: SheetRow, flight_start: date = MONTH_START, as_of: date | None = None) -> PricedFlight:
    """Price one row with the domain function the closing and the reads use. Each row has its own group and as_of."""
    schedule = schedule_of(row)
    (priced,) = price_flights(
        [schedule] if schedule is not None else [],
        PlatformRates(system=Decimal(1), by_line={row.number: row.platform_rate}),
        [facts_of(row, flight_start)],
        as_of if as_of is not None else flight_start + timedelta(days=(row.days_served or 1) - 1),
    )
    return priced
