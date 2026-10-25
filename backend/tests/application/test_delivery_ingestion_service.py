"""The nightly run: one request for the window, split by line, replacing what the window held."""

from datetime import date

from app.domain.value_objects.delivery import DeliveryDateRange, ExternalLineKey
from app.domain.value_objects.ingestion import MappedLine
from tests.fixtures.delivery_rows import daily_delivery, dsp_row
from tests.fixtures.ingestion_harness import DSP_ID, IngestionHarness

TODAY = date(2026, 8, 10)
LINE = 11
OTHER_LINE = 12
KEY = ExternalLineKey("100", "200")
OTHER_KEY = ExternalLineKey("100", "201")


def _mapped(line_id: int = LINE, key: ExternalLineKey = KEY) -> MappedLine:
    return MappedLine(campaign_line_id=line_id, key=key)


def test_the_run_asks_for_d_minus_7_to_d_minus_1():
    harness = IngestionHarness(mapped_lines=[_mapped()])

    harness.service.run(DSP_ID, TODAY)

    assert harness.client.requested_ranges == [DeliveryDateRange(date(2026, 8, 3), date(2026, 8, 9))]


def test_the_window_length_is_configurable():
    harness = IngestionHarness(mapped_lines=[_mapped()], window_days=3)

    harness.service.run(DSP_ID, TODAY)

    assert harness.client.requested_ranges == [DeliveryDateRange(date(2026, 8, 7), date(2026, 8, 9))]


def test_one_request_serves_every_mapped_line():
    harness = IngestionHarness(mapped_lines=[_mapped(LINE, KEY), _mapped(OTHER_LINE, OTHER_KEY)])

    harness.service.run(DSP_ID, TODAY)

    assert len(harness.client.requested_ranges) == 1


def test_one_request_is_made_even_when_no_line_is_mapped_because_the_catalogue_is_filled_from_it():
    harness = IngestionHarness(mapped_lines=[])

    result = harness.service.run(DSP_ID, TODAY)

    assert (len(harness.client.requested_ranges), result.stored_row_count) == (1, 0)


def test_delivery_is_stored_against_the_line_its_key_is_mapped_to():
    rows = [dsp_row(date(2026, 8, 5), KEY, impressions=700), dsp_row(date(2026, 8, 5), OTHER_KEY, impressions=300)]
    harness = IngestionHarness(rows=rows, mapped_lines=[_mapped(LINE, KEY), _mapped(OTHER_LINE, OTHER_KEY)])

    harness.service.run(DSP_ID, TODAY)

    assert harness.deliveries.impressions_by_line_and_day() == {
        (LINE, date(2026, 8, 5)): 700,
        (OTHER_LINE, date(2026, 8, 5)): 300,
    }


def test_an_integer_identifier_from_the_api_matches_the_text_stored_in_the_mapping():
    api_row = dsp_row(date(2026, 8, 5), ExternalLineKey.from_raw(100, 200), impressions=700)
    harness = IngestionHarness(rows=[api_row], mapped_lines=[MappedLine(LINE, ExternalLineKey.from_raw(" 100", "200 "))])

    harness.service.run(DSP_ID, TODAY)

    assert harness.deliveries.impressions_by_line_and_day() == {(LINE, date(2026, 8, 5)): 700}


def test_two_external_line_items_of_one_line_are_stored_as_one_summed_record():
    rows = [dsp_row(date(2026, 8, 5), KEY, impressions=700), dsp_row(date(2026, 8, 5), OTHER_KEY, impressions=300)]
    harness = IngestionHarness(rows=rows, mapped_lines=[_mapped(LINE, KEY), _mapped(LINE, OTHER_KEY)])

    result = harness.service.run(DSP_ID, TODAY)

    assert harness.deliveries.impressions_by_line_and_day() == {(LINE, date(2026, 8, 5)): 1000}
    assert result.stored_row_count == 1


def test_running_the_same_window_twice_leaves_one_set_of_rows():
    harness = IngestionHarness(rows=[dsp_row(date(2026, 8, 5), KEY)], mapped_lines=[_mapped()])

    harness.service.run(DSP_ID, TODAY)
    harness.service.run(DSP_ID, TODAY)

    assert len(harness.deliveries.rows) == 1


def test_a_restatement_replaces_the_window_and_leaves_older_days_alone():
    older = daily_delivery(LINE, date(2026, 7, 20), impressions=111)
    stale = daily_delivery(LINE, date(2026, 8, 6), impressions=999)
    harness = IngestionHarness(rows=[dsp_row(date(2026, 8, 5), KEY, impressions=700)], mapped_lines=[_mapped()],
                               existing=[older, stale])

    harness.service.run(DSP_ID, TODAY)

    assert harness.deliveries.impressions_by_line_and_day() == {
        (LINE, date(2026, 7, 20)): 111,
        (LINE, date(2026, 8, 5)): 700,
    }


def test_rows_whose_key_is_mapped_to_no_line_are_not_stored_and_are_counted():
    harness = IngestionHarness(rows=[dsp_row(date(2026, 8, 5), ExternalLineKey("9", "9"))], mapped_lines=[_mapped()])

    result = harness.service.run(DSP_ID, TODAY)

    assert (len(harness.deliveries.rows), result.unmatched_row_count) == (0, 1)
