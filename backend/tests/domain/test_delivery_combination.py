"""Several external line items mapped to one campaign line become one record per line and day."""

from datetime import date
from decimal import Decimal

from app.domain.services.delivery_combination import combine_daily_deliveries
from app.domain.value_objects.delivery import ExternalLineKey
from tests.fixtures.delivery_rows import dsp_row, external_key

DAY = date(2026, 8, 3)
BATCH = 7


def test_an_integer_identifier_from_the_api_matches_the_text_in_a_mapping():
    assert ExternalLineKey.from_raw(123, 456) == ExternalLineKey("123", "456")


def test_identifiers_are_compared_without_surrounding_whitespace():
    assert ExternalLineKey.from_raw(" 123 ", "456\n") == ExternalLineKey("123", "456")


def test_two_external_line_items_of_one_line_are_summed_into_one_record():
    first = dsp_row(DAY, external_key("c", "1"), impressions=1000, clicks=10, media_cost=Decimal("1.250000"),
                    measurable_impressions=900, viewable_impressions=700)
    second = dsp_row(DAY, external_key("c", "2"), impressions=500, clicks=5, media_cost=Decimal("0.750001"),
                     measurable_impressions=400, viewable_impressions=300)

    combined = combine_daily_deliveries([(1, first), (1, second)], ingestion_batch_id=BATCH)

    assert len(combined) == 1
    record = combined[0]
    assert (record.impressions, record.clicks, record.media_cost) == (1500, 15, Decimal("2.000001"))
    assert (record.measurable_impressions, record.viewable_impressions) == (1300, 1000)


def test_the_record_belongs_to_the_line_the_day_and_the_batch():
    combined = combine_daily_deliveries([(4, dsp_row(DAY))], ingestion_batch_id=BATCH)

    assert (combined[0].campaign_line_id, combined[0].delivery_date, combined[0].ingestion_batch_id) == (4, DAY, BATCH)


def test_rows_of_different_days_or_lines_stay_separate_and_come_back_ordered():
    rows = [
        (2, dsp_row(date(2026, 8, 4))),
        (1, dsp_row(date(2026, 8, 4))),
        (1, dsp_row(DAY)),
    ]

    combined = combine_daily_deliveries(rows, ingestion_batch_id=BATCH)

    assert [(r.campaign_line_id, r.delivery_date) for r in combined] == [
        (1, DAY),
        (1, date(2026, 8, 4)),
        (2, date(2026, 8, 4)),
    ]


def test_descriptive_attributes_are_kept_only_when_every_combined_row_agrees():
    agreeing = combine_daily_deliveries(
        [(1, dsp_row(DAY, external_key("c", "1"), banner_size="300x250")),
         (1, dsp_row(DAY, external_key("c", "2"), banner_size="300x250"))],
        ingestion_batch_id=BATCH,
    )
    differing = combine_daily_deliveries(
        [(1, dsp_row(DAY, external_key("c", "1"), banner_size="300x250")),
         (1, dsp_row(DAY, external_key("c", "2"), banner_size="728x90"))],
        ingestion_batch_id=BATCH,
    )

    assert (agreeing[0].banner_size, differing[0].banner_size) == ("300x250", None)


def test_rows_are_consumed_lazily_from_any_iterable():
    rows = ((1, dsp_row(DAY)) for _ in range(3))

    assert combine_daily_deliveries(rows, ingestion_batch_id=BATCH)[0].impressions == 3000
