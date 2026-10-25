"""GET /dsp-catalog: the Adform line catalogue for operations, filtered and paged, never with a cost."""

from datetime import date

import pytest

from app.domain.value_objects.catalog import CatalogLineObservation
from app.domain.value_objects.delivery import ExternalLineKey
from app.infrastructure.persistence.repositories.sqlalchemy_dsp_catalog_repository import (
    SqlAlchemyDspCatalogRepository,
)
from tests.fixtures.delivery_data import insert_campaign_line, insert_mapping, insert_other_dsp, seeded_dsp_id


def _observation(campaign: str, line_item: str, name: str = "Synthetic Line", campaign_name: str = "Synthetic Campaign",
                 last_seen: date = date(2026, 8, 9), impressions: date | None = date(2026, 8, 9)) -> CatalogLineObservation:
    return CatalogLineObservation(
        key=ExternalLineKey(campaign, line_item), campaign_name=campaign_name, line_item_name=name,
        line_start_date=date(2026, 7, 1), line_end_date=date(2026, 9, 30),
        first_seen_date=date(2026, 8, 1), last_seen_date=last_seen, last_impressions_date=impressions,
    )


@pytest.fixture
def dsp_id(test_db_session) -> int:
    return seeded_dsp_id(test_db_session)


def _seed(session, dsp_id: int, *observations: CatalogLineObservation) -> None:
    SqlAlchemyDspCatalogRepository(session).upsert_all(dsp_id, observations)


def _get(client, **params):
    return client.get("/dsp-catalog", params=params)


def test_an_item_carries_the_names_the_pair_the_dates_and_no_mapping(authenticated_client, test_db_session, dsp_id):
    _seed(test_db_session, dsp_id, _observation("100", "200", impressions=None))

    body = _get(authenticated_client).json()

    assert body["total"] == 1
    assert body["items"] == [{
        "dsp_id": dsp_id, "external_campaign_id": "100", "external_line_item_id": "200",
        "campaign_name": "Synthetic Campaign", "line_item_name": "Synthetic Line",
        "line_start_date": "2026-07-01", "line_end_date": "2026-09-30",
        "first_seen_date": "2026-08-01", "last_seen_date": "2026-08-09", "last_impressions_date": None,
        "mapped_line_id": None,
    }]


def test_a_mapped_pair_shows_the_line_it_is_mapped_to(authenticated_client, test_db_session, dsp_id):
    line = insert_campaign_line(test_db_session, dsp_id=dsp_id)
    insert_mapping(test_db_session, line, dsp_id, "100", "200")
    _seed(test_db_session, dsp_id, _observation("100", "200"), _observation("100", "201"))

    items = {i["external_line_item_id"]: i["mapped_line_id"] for i in _get(authenticated_client).json()["items"]}

    assert items == {"200": line, "201": None}


def test_mapped_true_and_false_split_the_catalogue(authenticated_client, test_db_session, dsp_id):
    line = insert_campaign_line(test_db_session, dsp_id=dsp_id)
    insert_mapping(test_db_session, line, dsp_id, "100", "200")
    _seed(test_db_session, dsp_id, _observation("100", "200"), _observation("100", "201"))

    mapped = _get(authenticated_client, mapped="true").json()["items"]
    unmapped = _get(authenticated_client, mapped="false").json()["items"]
    everything = _get(authenticated_client).json()["items"]

    assert ([i["external_line_item_id"] for i in mapped], [i["external_line_item_id"] for i in unmapped]) == (["200"], ["201"])
    assert len(everything) == 2


def test_q_matches_either_name_ignoring_case(authenticated_client, test_db_session, dsp_id):
    _seed(test_db_session, dsp_id,
          _observation("1", "1", name="Summer Banner", campaign_name="Alpha"),
          _observation("1", "2", name="Other", campaign_name="Winter SALE"),
          _observation("1", "3", name="Other", campaign_name="Beta"))

    by_line = _get(authenticated_client, q="summer").json()["items"]
    by_campaign = _get(authenticated_client, q="sale").json()["items"]

    assert ([i["external_line_item_id"] for i in by_line], [i["external_line_item_id"] for i in by_campaign]) == (["1"], ["2"])


def test_q_treats_percent_and_underscore_as_plain_text(authenticated_client, test_db_session, dsp_id):
    _seed(test_db_session, dsp_id, _observation("1", "1", name="100% done"), _observation("1", "2", name="1000 done"))

    items = _get(authenticated_client, q="100%").json()["items"]

    assert [i["external_line_item_id"] for i in items] == ["1"]


def test_dsp_id_filters_by_dsp(authenticated_client, test_db_session, dsp_id):
    other = insert_other_dsp(test_db_session)
    _seed(test_db_session, dsp_id, _observation("1", "1"))
    _seed(test_db_session, other, _observation("2", "2"))

    items = _get(authenticated_client, dsp_id=other).json()["items"]

    assert [(i["dsp_id"], i["external_campaign_id"]) for i in items] == [(other, "2")]


def test_active_since_keeps_the_pairs_last_seen_on_or_after_that_date(authenticated_client, test_db_session, dsp_id):
    _seed(test_db_session, dsp_id,
          _observation("1", "1", last_seen=date(2026, 8, 9)),
          _observation("1", "2", last_seen=date(2026, 8, 5)),
          _observation("1", "3", last_seen=date(2026, 8, 4)))

    items = _get(authenticated_client, active_since="2026-08-05").json()["items"]

    assert sorted(i["external_line_item_id"] for i in items) == ["1", "2"]


def test_items_come_newest_last_seen_first(authenticated_client, test_db_session, dsp_id):
    _seed(test_db_session, dsp_id,
          _observation("1", "1", last_seen=date(2026, 8, 5)), _observation("1", "2", last_seen=date(2026, 8, 9)))

    items = _get(authenticated_client).json()["items"]

    assert [i["external_line_item_id"] for i in items] == ["2", "1"]


def test_paging_defaults_to_fifty_and_reports_the_total(authenticated_client, test_db_session, dsp_id):
    _seed(test_db_session, dsp_id, *[_observation("1", str(n)) for n in range(60)])

    body = _get(authenticated_client).json()

    assert (len(body["items"]), body["total"], body["limit"], body["offset"]) == (50, 60, 50, 0)


def test_a_page_is_taken_with_limit_and_offset_without_overlap(authenticated_client, test_db_session, dsp_id):
    _seed(test_db_session, dsp_id, *[_observation("1", str(n)) for n in range(5)])

    first = _get(authenticated_client, limit=2, offset=0).json()["items"]
    second = _get(authenticated_client, limit=2, offset=2).json()["items"]

    assert len(first) == len(second) == 2
    assert not {i["external_line_item_id"] for i in first} & {i["external_line_item_id"] for i in second}


@pytest.mark.parametrize("params", [{"limit": 201}, {"limit": 0}, {"offset": -1}, {"mapped": "maybe"}, {"active_since": "yesterday"}])
def test_invalid_paging_or_filters_are_rejected(authenticated_client, params):
    assert _get(authenticated_client, **params).status_code == 422


def test_200_is_the_largest_page(authenticated_client):
    assert _get(authenticated_client, limit=200).status_code == 200


def test_no_cost_reaches_the_response(authenticated_client, test_db_session, dsp_id):
    _seed(test_db_session, dsp_id, _observation("1", "1"))

    assert "cost" not in _get(authenticated_client).text.lower()


def test_reading_the_catalogue_requires_the_operations_role(authenticated_client_no_operations_role):
    response = _get(authenticated_client_no_operations_role)

    assert response.status_code == 403
    assert set(response.json()) == {"code", "message"}
