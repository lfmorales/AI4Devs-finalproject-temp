"""Smoke check of the Adform connector against the real account.

Asks for D-1 with one data request and prints only the shape of the answer: the final operation status,
counts, and the type of each column. It never prints a value, a name, an identifier or an amount from the
report. It writes nothing to the database and nothing to disk, and does not import the database layer.
The quota (500 data requests a day) is shared with the whole agency, so run it sparingly.

Run: ADFORM_CLIENT_ID=... ADFORM_CLIENT_SECRET=... python -m scripts.adform_smoke
"""

import os
import sys
import time
from collections.abc import Callable, Mapping
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import httpx

from app.domain.exceptions import DomainError, DspReportFailedError
from app.domain.value_objects.delivery import DeliveryDateRange
from app.infrastructure.dsp.adform_delivery_client import AdformDeliveryClient, AdformReport, is_unattributed

_REQUIRED_VARIABLES = ("ADFORM_CLIENT_ID", "ADFORM_CLIENT_SECRET")
_EUR = "EUR"
_COUNT_COLUMNS = ("campaignID", "lineItemID", "campaignCurrency", "impressions")


def main(
    environ: Mapping[str, str] | None = None,
    http_client: httpx.Client | None = None,
    out: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
    today: Callable[[], date] = date.today,
) -> int:
    variables = os.environ if environ is None else environ
    missing = [name for name in _REQUIRED_VARIABLES if not variables.get(name)]
    if missing:
        out(f"Missing environment variables: {', '.join(missing)}")
        return 2

    own_client = http_client is None
    http = http_client or httpx.Client(timeout=httpx.Timeout(30.0))
    try:
        client = AdformDeliveryClient(
            client_id=variables["ADFORM_CLIENT_ID"],
            client_secret=variables["ADFORM_CLIENT_SECRET"],
            http_client=http,
            sleep=sleep,
        )
        day = today() - timedelta(days=1)
        report = client.fetch_report(DeliveryDateRange(day, day))
    except DspReportFailedError as error:
        # The status is a state name, not data; the message is left out in case the DSP put detail in it.
        out(f"operation status: {error.status}" if error.status else "error: DspReportFailedError")
        return 1
    except DomainError as error:
        out(f"error: {type(error).__name__}")
        return 1
    except Exception as error:  # noqa: BLE001 - a smoke script reports the kind of failure and nothing else.
        out(f"error: unexpected {type(error).__name__}")
        return 1
    finally:
        if own_client:
            http.close()

    for line in summarize(report):
        out(line)
    return 0


def summarize(report: AdformReport) -> list[str]:
    lines = [f"operation status: {report.final_status}", f"rows: {len(report.rows)}"]
    missing = [name for name in _COUNT_COLUMNS if name not in report.column_headers]
    if missing:
        lines.append(f"counts unavailable, columns missing: {', '.join(missing)}")
    else:
        lines.extend(_counts(report))
    lines.append("columns:")
    lines.extend(f"  {header}: {kind}" for header, kind in _column_types(report))
    return lines


def _counts(report: AdformReport) -> list[str]:
    position = {name: report.column_headers.index(name) for name in _COUNT_COLUMNS}
    ignored = eur = unreadable = zero_attributed = zero_not_attributed = 0
    pairs: set[tuple[int, int]] = set()
    for row in report.rows:
        try:
            campaign_id = int(row[position["campaignID"]])
            line_item_id = int(row[position["lineItemID"]])
            currency = str(row[position["campaignCurrency"]])
            impressions = int(row[position["impressions"]])
        except (ValueError, TypeError, IndexError):
            unreadable += 1
            continue
        eur += currency == _EUR
        if impressions == 0:
            # Attributed here means a real line item reported in EUR, which is narrower than "not ignored".
            if line_item_id > 0 and currency == _EUR:
                zero_attributed += 1
            else:
                zero_not_attributed += 1
        if is_unattributed(line_item_id, currency):
            ignored += 1
        else:
            pairs.add((campaign_id, line_item_id))
    lines = [
        f"rows without an attributed line item (ignored): {ignored}",
        f"rows in {_EUR}: {eur}",
        f"distinct (campaign, line item) pairs among attributed rows: {len(pairs)}",
        f"rows with zero impressions, attributed (line item > 0, {_EUR}): {zero_attributed}",
        f"rows with zero impressions, not attributed: {zero_not_attributed}",
    ]
    if unreadable:
        lines.append(f"rows that could not be read: {unreadable}")
    return lines


def _column_types(report: AdformReport) -> list[tuple[str, str]]:
    types: list[tuple[str, str]] = []
    for index, header in enumerate(report.column_headers):
        kinds = {_kind(row[index]) for row in report.rows if index < len(row)}
        types.append((header, " | ".join(sorted(kinds)) or "no values"))
    return types


def _kind(value: Any) -> str:
    # bool before int: bool is a subclass of int.
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, Decimal | float):
        return "decimal"
    if isinstance(value, str):
        return "string"
    return "null" if value is None else "other"


if __name__ == "__main__":
    sys.exit(main())
