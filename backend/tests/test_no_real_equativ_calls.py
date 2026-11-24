"""No test reaches Equativ: a real HTTP request to its hosts fails at once, naming the host; a mock transport is served.

The real requests below go through a proxy on a closed local port, so that, should the guard ever be missing, they fail
on this machine instead of reaching Equativ.
"""

import asyncio

import httpx
import pytest

from tests.conftest import RealEquativRequestBlocked

CLOSED_LOCAL_PROXY = "http://127.0.0.1:9"
EQUATIV_URLS = [
    "https://demand-api.eqtv.io/async-report",
    "https://oauth.smartadserverapis.com/oauth2/token",
]


@pytest.mark.parametrize("url", EQUATIV_URLS)
def test_a_real_sync_request_to_equativ_is_blocked_naming_the_host(url: str) -> None:
    with httpx.Client(proxy=CLOSED_LOCAL_PROXY) as client:
        with pytest.raises(RealEquativRequestBlocked, match=httpx.URL(url).host):
            client.post(url)


@pytest.mark.parametrize("url", EQUATIV_URLS)
def test_a_real_async_request_to_equativ_is_blocked_naming_the_host(url: str) -> None:
    async def _send() -> None:
        async with httpx.AsyncClient(proxy=CLOSED_LOCAL_PROXY) as client:
            await client.post(url)

    with pytest.raises(RealEquativRequestBlocked, match=httpx.URL(url).host):
        asyncio.run(_send())


def test_a_subdomain_of_an_equativ_host_is_blocked_too() -> None:
    with httpx.Client(proxy=CLOSED_LOCAL_PROXY) as client:
        with pytest.raises(RealEquativRequestBlocked, match="reporting.eqtv.io"):
            client.get("https://reporting.eqtv.io/anything")


@pytest.mark.parametrize("url", EQUATIV_URLS)
def test_a_mock_transport_to_the_same_url_is_served(url: str) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"served": str(request.url)}))

    with httpx.Client(transport=transport) as client:
        response = client.post(url)

    assert response.json() == {"served": url}


def test_another_host_is_not_blocked_by_the_guard() -> None:
    # It reaches the closed local proxy and fails there, which shows the guard let it through.
    with httpx.Client(proxy=CLOSED_LOCAL_PROXY) as client:
        with pytest.raises(httpx.ConnectError):
            client.get("https://api.adform.com/v1/anything")
