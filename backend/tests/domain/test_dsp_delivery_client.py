from collections.abc import Iterator
from datetime import date

import pytest

from app.domain.services.dsp_delivery_client import DspDeliveryClient
from app.domain.value_objects.delivery import DeliveryDateRange
from tests.fixtures.delivery_rows import dsp_row, external_key
from tests.fixtures.dsp_delivery_client import InMemoryDspDeliveryClient

RANGE = DeliveryDateRange(start=date(2026, 8, 2), end=date(2026, 8, 4))


def test_the_interface_cannot_be_instantiated_without_both_methods():
    with pytest.raises(TypeError):
        DspDeliveryClient()  # type: ignore[abstract]


def test_the_in_memory_double_satisfies_the_interface():
    assert isinstance(InMemoryDspDeliveryClient(rows=[]), DspDeliveryClient)


def test_fetch_returns_only_rows_inside_the_range_bounds_included():
    client = InMemoryDspDeliveryClient(
        rows=[dsp_row(date(2026, 8, day)) for day in (1, 2, 3, 4, 5)],
    )

    fetched_dates = [row.delivery_date for row in client.fetch_delivery(RANGE)]

    assert fetched_dates == [date(2026, 8, 2), date(2026, 8, 3), date(2026, 8, 4)]


def test_fetch_streams_rows_instead_of_returning_a_list():
    client = InMemoryDspDeliveryClient(rows=[dsp_row(date(2026, 8, 2))])

    assert isinstance(client.fetch_delivery(RANGE), Iterator)


def test_resolving_a_known_identifier_pair_returns_its_key():
    known = external_key("campaign-9", "line-item-9")
    client = InMemoryDspDeliveryClient(rows=[], known_keys=[known])

    assert client.resolve_identifiers("campaign-9", "line-item-9") == known


def test_resolving_an_unknown_identifier_pair_returns_none():
    client = InMemoryDspDeliveryClient(rows=[], known_keys=[external_key()])

    assert client.resolve_identifiers("campaign-9", "line-item-9") is None
