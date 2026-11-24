"""A synthetic Equativ: the client-credentials token, one asynchronous report, its executions and its paginated preview.

Its answers have the shape the probes of 2026-11-24 saw: the creation answers 201 with the report id as a JSON string,
each execution carries a status and, once finished, a download link; the preview pages carry `metadata` with
`totalRows`, `previewRows` and `status`, the declared `columns` with their types, and `rows` whose keys are the output
names and whose values are all text. Every package, name and figure is invented; the package ids start at 900000001.
"""

import json
from collections.abc import Sequence
from typing import Any
from urllib.parse import parse_qs

import httpx

TOKEN_URL = "https://oauth.smartadserverapis.com/oauth2/token"
API_HOST = "demand-api.eqtv.io"
TOKEN_VALUE = "synthetic-equativ-access-token"
REPORT_ID = "00000000-0000-4000-8000-000000000001"
DOWNLOAD_URL = "https://downloads.example.invalid/synthetic-report.csv"
# The real preview refused a page larger than this with 403.
MAX_PAGE_LIMIT = 100

DIMENSIONS = ["day", "auctionPackageDealId", "auctionPackageDealName"]
METRICS = [
    "impressions", "companyCurrencySpend", "paidBuyerConnectCompanyVendorCostCompanyCurrency",
    "paidBuyerConnectThirdPartyVendorCostCompanyCurrency", "paidBuyerConnectAudienceVendorCostCompanyCurrency",
    "clicks", "viewableImpressions", "videoComplete",
]
COLUMN_TYPES = {"day": "STRING", "auctionPackageDealId": "INTEGER", "auctionPackageDealName": "STRING"} | {
    metric: "NUMERIC" for metric in METRICS
}
SUCCESS = "PostProcessingSuccessful"


def package_row(
    day: str = "2026-11-19T00:00:00",
    package_id: str = "900000001",
    name: str = "Synthetic Package One",
    impressions: str = "61628",
    spend: str = "338.954",
    revenue: str = "271.1632",
    third_party: str = "0",
    audience: str = "0",
    clicks: str = "12",
    viewable: str = "50111",
    video_complete: str = "0",
) -> dict[str, str]:
    """One day of one auction package, every value as text, keyed by the output names the client asks for."""
    return {
        "day": day, "auctionPackageDealId": package_id, "auctionPackageDealName": name,
        "impressions": impressions, "companyCurrencySpend": spend,
        "paidBuyerConnectCompanyVendorCostCompanyCurrency": revenue,
        "paidBuyerConnectThirdPartyVendorCostCompanyCurrency": third_party,
        "paidBuyerConnectAudienceVendorCostCompanyCurrency": audience,
        "clicks": clicks, "viewableImpressions": viewable, "videoComplete": video_complete,
    }


def many_rows(count: int) -> list[dict[str, str]]:
    """`count` rows of invented packages over November: one row per day and package, never repeated."""
    return [
        package_row(
            day=f"2026-11-{1 + index // 12:02d}T00:00:00", package_id=str(900000001 + index % 12),
            name=f"Synthetic Package {index % 12 + 1}", impressions=str(1000 + index), spend="5.5", revenue="4.4",
        )
        for index in range(count)
    ]


class FakeEquativ:
    def __init__(
        self,
        rows: Sequence[dict[str, str]] = (),
        statuses: Sequence[str] = ("PubSubPublishSuccessful", SUCCESS),
        token_status: int = 200,
        create_status: int = 201,
        total_rows: int | None = None,
        preview_status: str = "READY",
        columns: Sequence[str] | None = None,
        error_body: str = '{"title": "rejected"}',
        fail_with: Exception | None = None,
    ) -> None:
        self.requests: list[httpx.Request] = []
        self._rows = [dict(row) for row in rows]
        self._statuses = list(statuses)
        self._execution_calls = 0
        self._token_status = token_status
        self._create_status = create_status
        self._total_rows = len(self._rows) if total_rows is None else total_rows
        self._preview_status = preview_status
        self._columns = list(columns) if columns is not None else [*DIMENSIONS, *METRICS]
        self._error_body = error_body
        self._fail_with = fail_with

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self._handle))

    def paths(self) -> list[str]:
        return [f"{request.method} {request.url.host}{request.url.path}" for request in self.requests]

    def created_reports(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests if r.method == "POST" and r.url.path == "/async-report"]

    def token_requests(self) -> list[dict[str, list[str]]]:
        return [parse_qs(r.content.decode()) for r in self.requests if str(r.url) == TOKEN_URL]

    def preview_pages(self) -> list[tuple[int, int]]:
        return [
            (int(r.url.params["offset"]), int(r.url.params["limit"]))
            for r in self.requests if r.url.path.endswith("/preview")
        ]

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self._fail_with is not None:
            raise self._fail_with
        if str(request.url) == TOKEN_URL and request.method == "POST":
            if self._token_status != 200:
                return httpx.Response(self._token_status, text=self._error_body)
            return httpx.Response(200, json={"access_token": TOKEN_VALUE, "token_type": "Bearer", "expires_in": 86400})
        if request.url.host != API_HOST:
            return httpx.Response(404, text='{"title": "unknown host"}')
        path = request.url.path
        if request.method == "POST" and path == "/async-report":
            if self._create_status != 201:
                return httpx.Response(self._create_status, text=self._error_body)
            return httpx.Response(201, json=REPORT_ID)
        if request.method == "GET" and path == f"/async-report/{REPORT_ID}/executions":
            return httpx.Response(200, json=self._executions())
        if request.method == "GET" and path == f"/async-report/{REPORT_ID}/preview":
            return self._preview(request)
        return httpx.Response(404, text='{"title": "not found"}')

    def _executions(self) -> list[dict[str, Any]]:
        if not self._statuses:
            return []
        status = self._statuses[min(self._execution_calls, len(self._statuses) - 1)]
        self._execution_calls += 1
        finished = status == SUCCESS
        return [{
            "executionDate": "2026-11-24T09:47:52.599345+00:00",
            "status": status,
            "downloadUrl": DOWNLOAD_URL if finished else None,
        }]

    def _preview(self, request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        limit = int(request.url.params.get("limit", "100"))
        if limit > MAX_PAGE_LIMIT:
            return httpx.Response(403, text='{"title": "forbidden"}')
        page = [{key: row[key] for key in self._columns if key in row} for row in self._rows[offset:offset + limit]]
        body = {
            "metadata": {
                "totalRows": self._total_rows, "previewRows": len(page), "jsonSizeBytes": len(json.dumps(page)),
                "status": self._preview_status,
            },
            "columns": [{"name": name, "type": COLUMN_TYPES.get(name, "STRING")} for name in self._columns],
            "rows": page,
        }
        return httpx.Response(200, json=body)
