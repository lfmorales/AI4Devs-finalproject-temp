"""A synthetic Adform: token endpoint, asynchronous stats report, and a report built from made-up figures."""

import json
from collections.abc import Sequence
from typing import Any

import httpx

COLUMN_HEADERS = [
    "date", "campaignID", "lineItemID", "campaignCurrency",
    "impressions", "clicks", "cost", "measurableImpressions", "viewImpressionsIAB",
]
OPERATION_PATH = "/v1/buyer/stats/operations/op-1"
LOCATION_PATH = "/v1/buyer/stats/data/op-1"
TOKEN_VALUE = "synthetic-access-token"


def report_row(
    date_text: str = "2026-08-05T00:00:00",
    campaign_id: int = 1001,
    line_item_id: int = 2001,
    currency: str = "EUR",
    impressions: int = 1000,
    clicks: int = 10,
    cost: str = "12.5",
    measurable: int = 900,
    viewable: int = 700,
) -> list[Any]:
    return [date_text, campaign_id, line_item_id, currency, impressions, clicks, _Raw(cost), measurable, viewable]


class _Raw:
    """A number written exactly as given, so a six-decimal cost reaches the client as JSON text."""

    def __init__(self, text: str) -> None:
        self.text = text


def report_body(rows: Sequence[list[Any]], headers: Sequence[str] = COLUMN_HEADERS) -> str:
    def encode(value: Any) -> str:
        return value.text if isinstance(value, _Raw) else json.dumps(value)

    rendered_rows = "[" + ",".join("[" + ",".join(encode(cell) for cell in row) + "]" for row in rows) + "]"
    return '{"reportData": {"columnHeaders": %s, "columns": [], "rows": %s}}' % (json.dumps(list(headers)), rendered_rows)


class FakeAdform:
    def __init__(
        self,
        rows: Sequence[list[Any]] = (),
        statuses: Sequence[str] = ("succeeded",),
        token_status: int = 200,
        data_status: int = 202,
        headers: Sequence[str] = COLUMN_HEADERS,
        fail_with: Exception | None = None,
    ) -> None:
        self.requests: list[httpx.Request] = []
        self._report = report_body(rows, headers)
        self._statuses = list(statuses)
        self._token_status = token_status
        self._data_status = data_status
        self._fail_with = fail_with

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self._handle))

    def paths(self) -> list[str]:
        return [f"{request.method} {request.url.host}{request.url.path}" for request in self.requests]

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self._fail_with is not None:
            raise self._fail_with
        path = request.url.path
        if request.url.host == "id.adform.com" and path == "/sts/connect/token":
            if self._token_status != 200:
                return httpx.Response(self._token_status, json={"error": "invalid_client"})
            return httpx.Response(200, json={"access_token": TOKEN_VALUE, "token_type": "Bearer", "expires_in": 3600})
        if request.method == "POST" and path == "/v1/buyer/stats/data":
            if self._data_status != 202:
                return httpx.Response(self._data_status, json={"error": "rejected"})
            return httpx.Response(202, headers={"operation-location": OPERATION_PATH})
        if path == OPERATION_PATH:
            status = self._statuses.pop(0) if len(self._statuses) > 1 else self._statuses[0]
            return httpx.Response(200, json={"id": "op-1", "status": status, "createdAt": "2026-08-10T02:00:00Z",
                                             "lastActionAt": "2026-08-10T02:00:05Z", "location": LOCATION_PATH})
        if path == LOCATION_PATH:
            return httpx.Response(200, content=self._report, headers={"content-type": "application/json"})
        return httpx.Response(404)
