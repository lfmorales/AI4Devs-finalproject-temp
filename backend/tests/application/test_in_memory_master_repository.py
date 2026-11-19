"""The in-memory master repository of the registration tests returns channels the way the real one does."""

import asyncio

from tests.fixtures.in_memory_campaign_registration import InMemoryMasterRepository


def _metric(repository: InMemoryMasterRepository, channel_id: int) -> str:
    channel = asyncio.run(repository.get_channel(channel_id))
    assert channel is not None
    return str(channel.delivery_metric)


def test_a_channel_counts_impressions_unless_it_is_listed_as_ots() -> None:
    repository = InMemoryMasterRepository(ots_channel_ids=frozenset({3}))

    assert {channel_id: _metric(repository, channel_id) for channel_id in (1, 3)} == {1: "impressions", 3: "ots"}


def test_an_unknown_channel_is_still_not_found() -> None:
    repository = InMemoryMasterRepository(unknown_channel_ids=frozenset({9}))

    assert asyncio.run(repository.get_channel(9)) is None
