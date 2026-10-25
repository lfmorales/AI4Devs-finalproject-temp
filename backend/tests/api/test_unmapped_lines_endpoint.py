"""GET /campaign-lines/unmapped: the lines that have no DSP mapping yet, for operations."""

from datetime import date

from tests.fixtures.delivery_data import add_line_to_campaign, insert_campaign_line, insert_mapping, seeded_dsp_id


def test_a_line_without_a_mapping_is_listed_with_its_campaign_number_dates_and_dsp(authenticated_client, test_db_session):
    dsp_id = seeded_dsp_id(test_db_session)
    line = insert_campaign_line(
        test_db_session, campaign_name="Synthetic Spring", dsp_id=dsp_id,
        line_start=date(2026, 8, 3), line_end=date(2026, 8, 20),
    )

    response = authenticated_client.get("/campaign-lines/unmapped")

    assert response.status_code == 200
    assert response.json() == [{
        "id": line, "campaign_name": "Synthetic Spring", "line_number": 1,
        "start_date": "2026-08-03", "end_date": "2026-08-20", "dsp_id": dsp_id, "dsp_name": "Delivery fixture DSP",
    }]


def test_a_mapped_line_is_not_listed_even_if_the_mapping_is_not_validated(authenticated_client, test_db_session):
    dsp_id = seeded_dsp_id(test_db_session)
    validated = insert_campaign_line(test_db_session, campaign_name="First", dsp_id=dsp_id)
    unvalidated = add_line_to_campaign(test_db_session, validated, 2)
    free = add_line_to_campaign(test_db_session, validated, 3)
    insert_mapping(test_db_session, validated, dsp_id, "1", "1")
    insert_mapping(test_db_session, unvalidated, dsp_id, "1", "2", validated_at=None)

    listed = [item["id"] for item in authenticated_client.get("/campaign-lines/unmapped").json()]

    assert listed == [free]


def test_the_list_is_empty_when_every_line_is_mapped(authenticated_client, test_db_session):
    dsp_id = seeded_dsp_id(test_db_session)
    line = insert_campaign_line(test_db_session, dsp_id=dsp_id)
    insert_mapping(test_db_session, line, dsp_id)

    assert authenticated_client.get("/campaign-lines/unmapped").json() == []


def test_the_lines_come_ordered_by_campaign_name_then_line_number(authenticated_client, test_db_session):
    dsp_id = seeded_dsp_id(test_db_session)
    beta = insert_campaign_line(test_db_session, campaign_name="Beta", dsp_id=dsp_id)
    alpha = insert_campaign_line(test_db_session, campaign_name="Alpha", dsp_id=dsp_id)
    alpha_two = add_line_to_campaign(test_db_session, alpha, 2)

    listed = [item["id"] for item in authenticated_client.get("/campaign-lines/unmapped").json()]

    assert listed == [alpha, alpha_two, beta]


def test_no_cost_or_price_reaches_the_response(authenticated_client, test_db_session):
    insert_campaign_line(test_db_session, dsp_id=seeded_dsp_id(test_db_session))

    text = authenticated_client.get("/campaign-lines/unmapped").text.lower()

    assert "cost" not in text and "cpm" not in text and "price" not in text


def test_listing_requires_the_operations_role(authenticated_client_no_operations_role):
    response = authenticated_client_no_operations_role.get("/campaign-lines/unmapped")

    assert response.status_code == 403
    assert set(response.json()) == {"code", "message"}
