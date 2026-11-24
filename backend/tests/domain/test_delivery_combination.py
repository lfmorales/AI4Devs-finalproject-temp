"""Several external line items mapped to one campaign line become one record per line and day."""

from dataclasses import fields
from datetime import date
from decimal import Decimal

from app.domain.services.delivery_combination import combine_daily_deliveries
from app.domain.value_objects.delivery import DailyDelivery, ExternalLineKey
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


def test_ots_are_summed_next_to_the_impressions_and_never_replace_them() -> None:
    first = dsp_row(DAY, external_key("c", "1"), impressions=410, ots=Decimal("7500.5000"))
    second = dsp_row(DAY, external_key("c", "2"), impressions=90, ots=Decimal("1499.2500"))

    record = combine_daily_deliveries([(1, first), (1, second)], ingestion_batch_id=BATCH)[0]

    assert (record.impressions, record.ots) == (500, Decimal("8999.7500"))


def test_completions_are_summed_as_counts() -> None:
    # 1,000 impressions at a rate of 0.75 and 3 at 0.5 were already counted per row: 750 and 2 (1.5 half to even).
    first = dsp_row(DAY, external_key("c", "1"), impressions=1000, video_completions=750)
    second = dsp_row(DAY, external_key("c", "2"), impressions=3, video_completions=2)

    record = combine_daily_deliveries([(1, first), (1, second)], ingestion_batch_id=BATCH)[0]

    assert record.video_completions == 752


def test_a_single_row_keeps_its_own_ots_and_completions() -> None:
    record = combine_daily_deliveries(
        [(1, dsp_row(DAY, ots=Decimal("7500.1234"), video_completions=40615))], ingestion_batch_id=BATCH)[0]

    assert (record.ots, record.video_completions) == (Decimal("7500.1234"), 40615)


def test_no_rate_is_held_on_a_stored_delivery() -> None:
    names = {field.name for field in fields(DailyDelivery)}

    assert {"ots", "video_completions"} <= names
    assert not [name for name in names if "rate" in name]


def test_two_equativ_packages_of_one_line_sum_their_four_amounts_exactly() -> None:
    first = dsp_row(DAY, external_key("900000001", "900000001"), buyer_spend=Decimal("338.954"),
                    reported_revenue=Decimal("271.1632"), third_party_data_cost=Decimal("0.10"),
                    audience_data_cost=Decimal("1.25"))
    second = dsp_row(DAY, external_key("900000002", "900000002"), buyer_spend=Decimal("62.876"),
                     reported_revenue=Decimal("50.30080"), third_party_data_cost=Decimal("0.05"),
                     audience_data_cost=Decimal("0"))

    (record,) = combine_daily_deliveries([(1, first), (1, second)], ingestion_batch_id=BATCH)

    assert record.reported_revenue == Decimal("321.464000")
    assert record.buyer_spend == Decimal("401.830")
    assert (record.third_party_data_cost, record.audience_data_cost) == (Decimal("0.15"), Decimal("1.25"))


def test_a_single_row_keeps_its_own_four_amounts() -> None:
    row = dsp_row(DAY, buyer_spend=Decimal("338.954"), reported_revenue=Decimal("271.1632"),
                  third_party_data_cost=Decimal("0"), audience_data_cost=Decimal("1.25"))

    (record,) = combine_daily_deliveries([(1, row)], ingestion_batch_id=BATCH)

    assert (record.buyer_spend, record.reported_revenue, record.third_party_data_cost, record.audience_data_cost) == (
        Decimal("338.954"), Decimal("271.1632"), Decimal(0), Decimal("1.25"),
    )


def test_an_adform_row_without_amounts_combines_into_zeros() -> None:
    (record,) = combine_daily_deliveries([(1, dsp_row(DAY)), (1, dsp_row(DAY, external_key("c", "2")))], BATCH)

    assert (record.buyer_spend, record.reported_revenue, record.third_party_data_cost, record.audience_data_cost) == (
        Decimal(0), Decimal(0), Decimal(0), Decimal(0),
    )
