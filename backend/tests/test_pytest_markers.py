"""The slow marker is registered, and slow tests stay out of the default run but can be selected."""

import shlex

import pytest


def test_the_slow_marker_is_registered(pytestconfig: pytest.Config):
    markers = [line.split(":")[0].strip() for line in pytestconfig.getini("markers")]

    assert "slow" in markers


def test_slow_tests_are_excluded_by_default(pytestconfig: pytest.Config):
    addopts = shlex.split(" ".join(pytestconfig.getini("addopts")))

    assert addopts[addopts.index("-m") + 1] == "not slow"


def test_the_million_row_memory_test_is_marked_slow():
    from tests.application import test_ingestion_memory

    marks = [mark.name for mark in test_ingestion_memory.test_a_million_row_run_stays_within_a_bounded_amount_of_memory.pytestmark]

    assert "slow" in marks
