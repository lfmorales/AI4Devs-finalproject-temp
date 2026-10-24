"""The indexes period roll-ups and mapping lookups rely on exist after migration."""

from sqlalchemy import inspect


def _indexed_columns(test_engine, table_name: str) -> set[tuple[str, ...]]:
    indexes = inspect(test_engine).get_indexes(table_name)
    unique_constraints = inspect(test_engine).get_unique_constraints(table_name)
    return {tuple(index["column_names"]) for index in indexes} | {
        tuple(constraint["column_names"]) for constraint in unique_constraints
    }


def test_delivery_date_is_indexed(test_engine):
    assert ("delivery_date",) in _indexed_columns(test_engine, "daily_deliveries")


def test_delivery_line_and_date_are_covered_by_the_grain_constraint(test_engine):
    assert ("campaign_line_id", "delivery_date") in _indexed_columns(test_engine, "daily_deliveries")


def test_campaign_period_of_a_line_is_indexed(test_engine):
    assert ("campaign_period_id",) in _indexed_columns(test_engine, "campaign_lines")


def test_dsp_mapping_is_indexed_by_line_and_by_external_identifiers(test_engine):
    indexed = _indexed_columns(test_engine, "dsp_mappings")

    assert ("campaign_line_id",) in indexed
    assert ("dsp_id", "external_campaign_id", "external_line_item_id") in indexed
