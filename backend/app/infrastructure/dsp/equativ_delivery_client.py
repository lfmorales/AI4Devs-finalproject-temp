"""Equativ demand API client: one asynchronous report per run, read through its paginated preview.

The report is created with `POST /async-report` (the synchronous `POST /report` gives figures Equativ declares invalid),
with no scheduling and no post-processing, so Equativ sends no email and writes no file. Its execution is polled until
`PostProcessingSuccessful`; its rows are then read from `GET /async-report/{id}/preview`, a page of 100 at a time, until
the preview's `totalRows`. The download link is never fetched and the report is never deleted. Equativ bills in UTC, so
the window's dates are asked as UTC days, the end date being exclusive.

One row is one day of one auction package, keyed by `auctionPackageDealId`. Every value arrives as text; amounts are
read as exact decimals, never through a binary float. Equativ reports no media cost: the buyer's spend is what the buyer
pays, not what GeoQ pays. Nothing here logs or raises with a credential, a token, a response body or a cell's value.
"""

import logging
import time
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from pydantic import SecretStr

from app.domain.exceptions import (
    DspAuthenticationError,
    DspNotSupportedError,
    DspReportFailedError,
    DspReportTimeoutError,
    DspResponseFormatError,
    DspUnreachableError,
)
from app.domain.services.dsp_delivery_client import DspDeliveryClient
from app.domain.value_objects.delivery import DeliveryDateRange, DspDeliveryRow, ExternalLineKey, LineCatalogInfo

logger = logging.getLogger(__name__)

TOKEN_URL = "https://oauth.smartadserverapis.com/oauth2/token"
API_BASE_URL = "https://demand-api.eqtv.io"
REPORT_TIMEZONE = "Etc/UTC"
USE_CASE = "RTB"
SUCCEEDED = "PostProcessingSuccessful"
# Equativ names its failures in the status itself; any other status is a step on the way.
_FAILURE_MARKERS = ("fail", "error", "cancel", "abort")
# The real preview refuses a larger page with 403.
PAGE_SIZE = 100

_DAY = "day"
_PACKAGE_ID = "auctionPackageDealId"
_PACKAGE_NAME = "auctionPackageDealName"
_IMPRESSIONS = "impressions"
_BUYER_SPEND = "companyCurrencySpend"
# Equativ's «Total Curator Margin»: GeoQ's revenue, 80 % of the buyer's spend on every row of the probes.
_REPORTED_REVENUE = "paidBuyerConnectCompanyVendorCostCompanyCurrency"
_THIRD_PARTY_DATA_COST = "paidBuyerConnectThirdPartyVendorCostCompanyCurrency"
_AUDIENCE_DATA_COST = "paidBuyerConnectAudienceVendorCostCompanyCurrency"
_CLICKS = "clicks"
_VIEWABLE_IMPRESSIONS = "viewableImpressions"
_VIDEO_COMPLETE = "videoComplete"

DIMENSIONS = [_DAY, _PACKAGE_ID, _PACKAGE_NAME]
METRICS = [
    _IMPRESSIONS, _BUYER_SPEND, _REPORTED_REVENUE, _THIRD_PARTY_DATA_COST, _AUDIENCE_DATA_COST, _CLICKS,
    _VIEWABLE_IMPRESSIONS, _VIDEO_COMPLETE,
]
_REQUIRED_COLUMNS = [*DIMENSIONS, *METRICS]
# A package id that names no package: the row is delivery without an attributed package.
_NO_PACKAGE = ("", "0")


class EquativDeliveryClient(DspDeliveryClient):
    def __init__(
        self,
        client_id: str,
        client_secret: str | SecretStr,
        http_client: httpx.Client,
        poll_interval_seconds: float = 30.0,
        max_wait_seconds: float = 15 * 60.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        token_url: str = TOKEN_URL,
        api_base_url: str = API_BASE_URL,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret if isinstance(client_secret, SecretStr) else SecretStr(client_secret)
        self._http = http_client
        self._poll_interval_seconds = poll_interval_seconds
        self._max_wait_seconds = max_wait_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._token_url = token_url
        self._api_base = httpx.URL(api_base_url)
        # The id of the report the latest run created, for the batch to record as its source.
        self.last_report_id: str | None = None
        self._source_listener: Callable[[str], None] | None = None

    def on_source_known(self, listener: Callable[[str], None]) -> None:
        self._source_listener = listener

    def __repr__(self) -> str:
        return "EquativDeliveryClient()"

    def fetch_delivery(self, date_range: DeliveryDateRange) -> Iterator[DspDeliveryRow]:
        """Stream the rows of one report for the range, bounds included, as the preview pages arrive."""
        headers = {"Authorization": f"Bearer {self._request_token()}"}
        report_id = self._create_report(date_range, headers)
        # Named before the wait: a run that fails while waiting or reading still records its report.
        self.last_report_id = report_id
        if self._source_listener is not None:
            self._source_listener(report_id)
        self._wait_for_report(report_id, headers)
        for cells in self._preview_rows(report_id, headers):
            yield _to_delivery_row(cells)

    def resolve_identifiers(self, external_campaign_id: str, external_line_item_id: str) -> ExternalLineKey | None:
        """Never asked: an Equativ mapping is validated by the user who writes the package id."""
        raise DspNotSupportedError("Equativ identifiers are validated by the user, not checked with Equativ")

    def _request_token(self) -> str:
        response = self._send(
            "POST",
            self._token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret.get_secret_value(),
            },
        )
        token = _json(response).get("access_token")
        if not isinstance(token, str) or not token:
            raise DspResponseFormatError("The token response carries no access token")
        return token

    def _create_report(self, date_range: DeliveryDateRange, headers: dict[str, str]) -> str:
        end_exclusive = date_range.end + timedelta(days=1)
        body = {
            "name": f"adops360-{date_range.start.isoformat()}-{date_range.end.isoformat()}",
            "startDate": _utc_midnight(date_range.start),
            "endDate": _utc_midnight(end_exclusive),
            "dimensions": [{"field": field, "outputName": field} for field in DIMENSIONS],
            "metrics": [{"field": field, "outputName": field} for field in METRICS],
            "filters": [],
            "timezone": REPORT_TIMEZONE,
            "useCaseId": USE_CASE,
        }
        logger.info("Requesting an Equativ report for %s to %s", date_range.start, date_range.end)
        response = self._send("POST", str(self._api_base.join("/async-report")), json=body, headers=headers)
        if response.status_code != 201:
            raise DspResponseFormatError("The report was not created")
        try:
            report_id = response.json()
        except ValueError:
            raise DspResponseFormatError("The created report carries no id") from None
        if not isinstance(report_id, str) or not report_id:
            raise DspResponseFormatError("The created report carries no id")
        return report_id

    def _wait_for_report(self, report_id: str, headers: dict[str, str]) -> None:
        started = self._monotonic()
        url = str(self._api_base.join(f"/async-report/{report_id}/executions"))
        while True:
            response = self._send("GET", url, headers=headers)
            try:
                executions = response.json()
            except ValueError:
                raise DspResponseFormatError("The executions are not valid JSON") from None
            if not isinstance(executions, list):
                raise DspResponseFormatError("The executions are not a list")
            status = str(executions[-1].get("status")) if executions and isinstance(executions[-1], dict) else ""
            if status == SUCCEEDED:
                return
            if any(marker in status.lower() for marker in _FAILURE_MARKERS):
                raise DspReportFailedError(f"The Equativ report ended with status '{status}'", status=status)
            if self._monotonic() - started + self._poll_interval_seconds > self._max_wait_seconds:
                raise DspReportTimeoutError("The Equativ report had not finished within the allowed time")
            logger.info("Equativ report still running (status %s)", status or "none yet")
            self._sleep(self._poll_interval_seconds)

    def _preview_rows(self, report_id: str, headers: dict[str, str]) -> Iterator[dict[str, Any]]:
        url = str(self._api_base.join(f"/async-report/{report_id}/preview"))
        read = 0
        while True:
            page = _json(self._send("GET", url, params={"offset": read, "limit": PAGE_SIZE}, headers=headers))
            metadata = page.get("metadata")
            rows = page.get("rows")
            if not isinstance(metadata, dict) or metadata.get("status") != "READY":
                raise DspResponseFormatError("The report preview is not ready")
            total = metadata.get("totalRows")
            if not isinstance(total, int) or not isinstance(rows, list):
                raise DspResponseFormatError("The report preview lacks its total or its rows")
            for cells in rows:
                if not isinstance(cells, dict):
                    raise DspResponseFormatError("A preview row is not an object")
                yield cells
            read += len(rows)
            if read == total:
                return
            if not rows or read > total:
                raise DspResponseFormatError("The report preview yielded a different number of rows than its total")

    def _send(self, method: str, url: str, **options: Any) -> httpx.Response:
        try:
            response = self._http.request(method, url, **options)
        except httpx.TransportError:
            # No detail from the library: it may name hosts and is of no use to the caller.
            raise DspUnreachableError("Equativ could not be reached") from None
        if response.status_code in (401, 403):
            raise DspAuthenticationError("Equativ refused the credentials, the token or the fields asked for")
        if response.status_code >= 400:
            raise DspReportFailedError(f"Equativ answered HTTP {response.status_code}")
        return response


def _utc_midnight(day: date) -> str:
    return f"{day.isoformat()}T00:00:00.000Z"


def _to_delivery_row(cells: dict[str, Any]) -> DspDeliveryRow:
    missing = [name for name in _REQUIRED_COLUMNS if name not in cells]
    if missing:
        raise DspResponseFormatError(f"The report lacks the columns {', '.join(missing)}")
    package_id = str(cells[_PACKAGE_ID]).strip() if cells[_PACKAGE_ID] is not None else ""
    if package_id in _NO_PACKAGE:
        key, catalog = None, None
    else:
        if not package_id.isdigit():
            raise DspResponseFormatError(f"The column {_PACKAGE_ID} holds a value that is not a package id")
        key = ExternalLineKey.from_raw(package_id, package_id)
        name = str(cells[_PACKAGE_NAME])
        catalog = LineCatalogInfo(name, name, None, None)
    return DspDeliveryRow(
        key=key,
        delivery_date=_day(cells[_DAY]),
        impressions=_whole(cells, _IMPRESSIONS),
        clicks=_whole(cells, _CLICKS),
        # Equativ reports no media cost: the buyer's spend is never one.
        media_cost=Decimal(0),
        measurable_impressions=0,
        viewable_impressions=_whole(cells, _VIEWABLE_IMPRESSIONS),
        banner_size=None,
        screen=None,
        line_format=None,
        ots=Decimal(0),
        video_completions=_whole(cells, _VIDEO_COMPLETE),
        buyer_spend=_amount(cells, _BUYER_SPEND),
        reported_revenue=_amount(cells, _REPORTED_REVENUE),
        third_party_data_cost=_amount(cells, _THIRD_PARTY_DATA_COST),
        audience_data_cost=_amount(cells, _AUDIENCE_DATA_COST),
        catalog=catalog,
    )


def _text(cells: dict[str, Any], column: str) -> str:
    value = cells[column]
    if value is None or str(value).strip() == "":
        raise DspResponseFormatError(f"The column {column} holds an empty cell")
    return str(value).strip()


def _whole(cells: dict[str, Any], column: str) -> int:
    text = _text(cells, column)
    if not text.isdigit():
        raise DspResponseFormatError(f"The column {column} holds a value that is not a whole number")
    return int(text)


def _amount(cells: dict[str, Any], column: str) -> Decimal:
    try:
        amount = Decimal(_text(cells, column))
    except InvalidOperation:
        raise DspResponseFormatError(f"The column {column} holds a value that is not a number") from None
    if not amount.is_finite():
        raise DspResponseFormatError(f"The column {column} holds a value that is not a number")
    return amount


def _day(value: Any) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise DspResponseFormatError(f"The column {_DAY} holds a value that is not a date") from None


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        return dict(response.json())
    except (ValueError, TypeError):
        raise DspResponseFormatError("The response is not valid JSON") from None
