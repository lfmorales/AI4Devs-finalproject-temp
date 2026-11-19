"""GET /masters/channels returns each channel with its delivery metric, to every role that reads the masters."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

EXPECTED_METRICS = {"Directo": "impressions", "Deal": "impressions", "DOOH": "ots", "CTV": "impressions"}


@pytest.mark.parametrize("role", ["operations", "business", "finance"])
def test_each_channel_carries_its_delivery_metric(client_for_roles: Callable[..., TestClient], role: str) -> None:
    response = client_for_roles(role).get("/masters/channels")

    assert response.status_code == 200
    assert {channel["name"]: channel["delivery_metric"] for channel in response.json()} == EXPECTED_METRICS
    assert all(set(channel) == {"id", "name", "delivery_metric"} for channel in response.json())
