"""Adform buyer stats client.

The stats report is asynchronous: the request is accepted with an operation location, the operation is
polled until it has succeeded, and only then is the report read. The quota (10 requests a minute, 500 a
day) is shared by the whole agency, so one report serves a whole run. Nothing here logs or raises with a
credential, a token or a response body.
"""

import json
import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from pydantic import SecretStr

from app.domain.exceptions import (
    DspAuthenticationError,
    DspReportFailedError,
    DspReportTimeoutError,
    DspResponseFormatError,
    DspUnreachableError,
    UnsupportedCurrencyError,
)
from app.domain.services.dsp_delivery_client import DspDeliveryClient
from app.domain.value_objects.delivery import DeliveryDateRange, DspDeliveryRow, ExternalLineKey, LineCatalogInfo

logger = logging.getLogger(__name__)

TOKEN_URL = "https://id.adform.com/sts/connect/token"
API_BASE_URL = "https://api.adform.com"
DATA_PATH = "/v1/buyer/stats/data"
SCOPES = "https://api.adform.com/scope/buyer.stats https://api.adform.com/scope/eapi"
MIN_POLL_INTERVAL_SECONDS = 3.0
IDENTIFIER_LOOKBACK_DAYS = 30

# Eight dimensions, the API's maximum. The names and dates do not change the grain: one row per date, campaign and line.
_DIMENSIONS = [
    "date", "campaignID", "campaign", "lineItemID", "lineItem", "lineItemStartDate", "lineItemEndDate",
    "campaignCurrency",
]
_METRICS = ["impressions", "clicks", "cost", "measurableImpressions", "viewImpressionsIAB"]
_REQUIRED_COLUMNS = [*_DIMENSIONS, *_METRICS]
_REPORTED_CURRENCY = "EUR"
_NO_CURRENCY = "-"


@dataclass(frozen=True)
class AdformReport:
    """A finished stats report as Adform returns it, before any row is interpreted."""

    final_status: str
    column_headers: list[str]
    rows: list[list[Any]]


def is_unattributed(line_item_id: int, currency: str) -> bool:
    """Adform reports delivery it does not attribute to a line item with a non-positive id and no currency."""
    return line_item_id <= 0 and currency == _NO_CURRENCY


class AdformDeliveryClient(DspDeliveryClient):
    def __init__(
        self,
        client_id: str,
        client_secret: str | SecretStr,
        http_client: httpx.Client,
        poll_interval_seconds: float = MIN_POLL_INTERVAL_SECONDS,
        max_poll_attempts: int = 60,
        sleep: Callable[[float], None] = time.sleep,
        today: Callable[[], date] = date.today,
        token_url: str = TOKEN_URL,
        api_base_url: str = API_BASE_URL,
    ) -> None:
        if poll_interval_seconds < MIN_POLL_INTERVAL_SECONDS:
            raise ValueError(f"poll_interval_seconds must be at least {MIN_POLL_INTERVAL_SECONDS}")
        self._client_id = client_id
        self._client_secret = client_secret if isinstance(client_secret, SecretStr) else SecretStr(client_secret)
        self._http = http_client
        self._poll_interval_seconds = poll_interval_seconds
        self._max_poll_attempts = max_poll_attempts
        self._sleep = sleep
        self._today = today
        self._token_url = token_url
        self._api_base = httpx.URL(api_base_url)

    def fetch_delivery(self, date_range: DeliveryDateRange) -> Iterator[DspDeliveryRow]:
        # The report is parsed whole: it is bounded by the window (a few tens of thousands of rows).
        yield from self._rows(self.fetch_report(date_range))

    def fetch_report(self, date_range: DeliveryDateRange) -> AdformReport:
        """One data request: token, accepted operation, polling, then the finished report as Adform sent it."""
        token = self._request_token()
        headers = {"Authorization": f"Bearer {token}"}
        operation_path = self._request_report(date_range, headers)
        location = self._wait_for_report(operation_path, headers)
        document = self._read_report(location, headers)
        try:
            data = document["reportData"]
            return AdformReport("succeeded", list(data["columnHeaders"]), [list(row) for row in data["rows"]])
        except (KeyError, TypeError):
            raise DspResponseFormatError("The report lacks its data") from None

    def resolve_identifiers(self, external_campaign_id: str, external_line_item_id: str) -> ExternalLineKey | None:
        """Return the key if the pair appears in any delivery row of the last 30 days, else None.

        Limitation of the stats API: it reports delivery, not configuration. A line item that exists but
        delivered nothing in the period cannot be told apart from one that does not exist, so both come
        back as None. An unreachable DSP raises DspUnreachableError instead; it is never reported as unknown.
        """
        candidate = ExternalLineKey.from_raw(external_campaign_id, external_line_item_id)
        today = self._today()
        lookback = DeliveryDateRange(today - timedelta(days=IDENTIFIER_LOOKBACK_DAYS), today - timedelta(days=1))
        for row in self.fetch_delivery(lookback):
            if row.key == candidate:
                return row.key
        return None

    def _request_token(self) -> str:
        response = self._send(
            "POST",
            self._token_url,
            auth=(self._client_id, self._client_secret.get_secret_value()),
            data={"grant_type": "client_credentials", "scope": SCOPES},
        )
        token = _json(response).get("access_token")
        if not isinstance(token, str) or not token:
            raise DspResponseFormatError("The token response carries no access token")
        return token

    def _request_report(self, date_range: DeliveryDateRange, headers: dict[str, str]) -> str:
        body = {
            "dimensions": _DIMENSIONS,
            "metrics": _METRICS,
            "filter": {"date": {"from": date_range.start.isoformat(), "to": date_range.end.isoformat()}},
            "paging": {"limit": 0},
        }
        logger.info("Requesting Adform report for %s to %s", date_range.start, date_range.end)
        response = self._send("POST", str(self._api_base.join(DATA_PATH)), json=body, headers=headers)
        operation_location = response.headers.get("operation-location")
        if response.status_code != 202 or not operation_location:
            raise DspResponseFormatError("The report request was not accepted as an asynchronous operation")
        return operation_location

    def _wait_for_report(self, operation_path: str, headers: dict[str, str]) -> str:
        for attempt in range(1, self._max_poll_attempts + 1):
            operation = _json(self._send("GET", str(self._api_base.join(operation_path)), headers=headers))
            status = operation.get("status")
            if status == "succeeded":
                location = operation.get("location")
                if not isinstance(location, str) or not location:
                    raise DspResponseFormatError("The finished operation carries no report location")
                return location
            if status != "running":
                raise DspReportFailedError(f"The Adform report ended with status '{status}'", status=str(status))
            logger.info("Adform report still running (attempt %s of %s)", attempt, self._max_poll_attempts)
            if attempt < self._max_poll_attempts:
                self._sleep(self._poll_interval_seconds)
        raise DspReportTimeoutError("The Adform report was still running after the allowed polling attempts")

    def _read_report(self, location: str, headers: dict[str, str]) -> dict[str, Any]:
        response = self._send("GET", str(self._api_base.join(location)), headers=headers)
        # parse_float=Decimal: a six-decimal cost must not pass through a binary float.
        try:
            return dict(json.loads(response.content, parse_float=Decimal))
        except (ValueError, TypeError):
            raise DspResponseFormatError("The report is not valid JSON") from None

    def _send(self, method: str, url: str, **options: Any) -> httpx.Response:
        try:
            response = self._http.request(method, url, **options)
        except httpx.TransportError:
            # No detail from the library: it may name hosts and is of no use to the caller.
            raise DspUnreachableError("Adform could not be reached") from None
        if response.status_code == 401:
            raise DspAuthenticationError("Adform refused the credentials or the token")
        if response.status_code >= 400:
            raise DspReportFailedError(f"Adform answered HTTP {response.status_code}")
        return response

    def _rows(self, report: AdformReport) -> Iterator[DspDeliveryRow]:
        headers, rows = report.column_headers, report.rows
        missing = [name for name in _REQUIRED_COLUMNS if name not in headers]
        if missing:
            raise DspResponseFormatError(f"The report lacks the columns {', '.join(missing)}")
        position = {name: headers.index(name) for name in _REQUIRED_COLUMNS}
        for raw_row in rows:
            yield self._to_delivery_row({name: raw_row[index] for name, index in position.items()})

    @staticmethod
    def _to_delivery_row(cells: dict[str, Any]) -> DspDeliveryRow:
        try:
            line_item_id = int(cells["lineItemID"])
            currency = str(cells["campaignCurrency"])
            catalog = None
            if is_unattributed(line_item_id, currency):
                key = None  # Delivery Adform does not attribute to a line item.
            elif currency != _REPORTED_CURRENCY:
                raise UnsupportedCurrencyError("The report contains a currency other than EUR")
            else:
                key = ExternalLineKey.from_raw(int(cells["campaignID"]), line_item_id)
                catalog = LineCatalogInfo(
                    str(cells["campaign"]), str(cells["lineItem"]),
                    _date_or_none(cells["lineItemStartDate"]), _date_or_none(cells["lineItemEndDate"]),
                )
            return DspDeliveryRow(
                key=key,
                delivery_date=date.fromisoformat(str(cells["date"])[:10]),
                impressions=int(cells["impressions"]),
                clicks=int(cells["clicks"]),
                media_cost=Decimal(cells["cost"]),
                measurable_impressions=int(cells["measurableImpressions"]),
                viewable_impressions=int(cells["viewImpressionsIAB"]),
                banner_size=None,
                screen=None,
                line_format=None,
                catalog=catalog,
            )
        except (ValueError, TypeError, InvalidOperation):
            raise DspResponseFormatError("A report row holds a value of an unexpected type") from None


def _date_or_none(value: Any) -> date | None:
    """The date part of a `YYYY-MM-DDTHH:MM:SS` text; a missing or unreadable one is None, not a failed run."""
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        return dict(response.json())
    except (ValueError, TypeError):
        raise DspResponseFormatError("The response is not valid JSON") from None
