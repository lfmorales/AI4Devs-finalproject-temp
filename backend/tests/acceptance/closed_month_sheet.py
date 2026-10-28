"""The private closed-month sheet (one anonymised campaign per row) and the domain pricing of its rows.

The file lives in tests/private/, which is ignored by git: it is read here with the csv module and never copied.
Every figure of the comparison comes from the sheet's own columns; none is written in the tests.
"""

import csv
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from app.domain.services.priced_flights import price_flights
from app.domain.value_objects.priced_flight import FlightFacts, PlatformRates, PricedFlight
from app.domain.value_objects.rebate import Bracket, RebateSchedule

SHEET_PATH = Path(__file__).resolve().parents[1] / "private" / "mes_cerrado_directo.csv"
SKIP_REASON = f"the private sheet {SHEET_PATH.name} is not present in tests/private/ (it is ignored by git)"

FLIGHT_START = date(2026, 8, 1)
FLIGHT_END = date(2026, 8, 31)
# Later than the end of the flight, so every row is a closed month.
AS_OF = date(2026, 9, 5)

# Rows with no contracted volume are not part of this cut: their delivery has no line to hang from and stays as
# unmatched delivery in the exception queue. They are left out of every comparison.
EXCLUDED_REASON = "sin volumen contratado: no contemplada en este corte; su entrega queda como entrega sin casar"

_ZERO = Decimal(0)


@dataclass(frozen=True)
class SheetRow:
    """One row of the sheet, as the sheet states it. Amounts are Decimals read from the text of the file."""

    number: int
    campaign: str
    served_impressions: int
    purchase_cost: Decimal
    rebate_rate: Decimal | None  # None: the sheet has "-", a campaign without a rebate schedule
    oc_impressions: Decimal
    oc_cpm: Decimal
    platform_cpm: Decimal
    sale: Decimal
    total_cost: Decimal
    margin: Decimal
    margin_pct: Decimal | None  # as the sheet states it: a fraction, 0.2096 for 20.96 %; None where it has "-"

    @property
    def contracted_impressions(self) -> int:
        """The domain takes whole impressions: the volume is rounded to the nearest one, half up."""
        return int(self.oc_impressions.quantize(Decimal(1), rounding=ROUND_HALF_UP))

    @property
    def sheet_rebate(self) -> Decimal:
        return (self.rebate_rate or _ZERO) * self.sale

    @property
    def sheet_platform_cost(self) -> Decimal:
        return Decimal(self.served_impressions) / Decimal(1000) * self.platform_cpm


def load_rows(path: Path = SHEET_PATH) -> list[SheetRow]:
    rows: list[SheetRow] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for number, raw in enumerate(csv.DictReader(handle), start=1):
            rebate = raw["rebate_rate"].strip()
            margin_pct = raw["margin_pct"].strip().strip("'\"")
            rows.append(SheetRow(
                number=number,
                campaign=raw["campaign"],
                served_impressions=int(Decimal(raw["served_impressions"])),
                purchase_cost=Decimal(raw["purchase_cost"]),
                rebate_rate=None if rebate == "-" else Decimal(rebate),
                oc_impressions=Decimal(raw["oc_impressions"]),
                oc_cpm=Decimal(raw["oc_cpm"]),
                platform_cpm=Decimal(raw["platform_cpm"]),
                sale=Decimal(raw["sale"]),
                total_cost=Decimal(raw["total_cost"]),
                margin=Decimal(raw["margin"]),
                margin_pct=None if margin_pct == "-" else Decimal(margin_pct),
            ))
    return rows


def split_rows(rows: list[SheetRow]) -> tuple[list[SheetRow], list[SheetRow]]:
    """The rows compared (contracted volume above zero) and the rows left out (none)."""
    compared = [row for row in rows if row.oc_impressions > 0]
    excluded = [row for row in rows if row.oc_impressions == 0]
    return compared, excluded


def facts_of(row: SheetRow) -> FlightFacts:
    """A line with one whole-month flight in its own holding group, so that no row shares a counter with another."""
    return FlightFacts(
        flight_id=row.number, campaign_line_id=row.number, campaign_id=row.number,
        flight_start=FLIGHT_START, flight_end=FLIGHT_END, group_id=row.number, agency_id=row.number,
        campaign_type_id=1, channel="Directo", channel_id=1, scope="national",
        contracted_impressions=row.contracted_impressions, sale_cpm=row.oc_cpm,
        delivered_impressions=row.served_impressions, media_cost=row.purchase_cost,
    )


def schedule_of(row: SheetRow) -> RebateSchedule | None:
    """A flat schedule at the sheet's rate for the row's own group; none when the sheet has "-"."""
    if row.rebate_rate is None:
        return None
    return RebateSchedule(
        schedule_id=row.number, group_id=row.number, agency_id=None, channel=None, scope=None,
        valid_from=date(2026, 1, 1), valid_to=None, brackets=(Bracket(Decimal(0), None, row.rebate_rate),),
    )


def price_rows(rows: list[SheetRow]) -> dict[int, PricedFlight]:
    """Price the rows with the domain function the closing and the reads use; the platform rate is each row's own."""
    schedules = [schedule for schedule in (schedule_of(row) for row in rows) if schedule is not None]
    platform_rates = PlatformRates(system=Decimal(1), by_line={row.number: row.platform_cpm for row in rows})
    priced = price_flights(schedules, platform_rates, [facts_of(row) for row in rows], AS_OF)
    return {item.facts.flight_id: item for item in priced}
