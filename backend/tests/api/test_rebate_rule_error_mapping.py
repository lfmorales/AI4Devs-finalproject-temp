"""Rebate rule errors leave through the global handlers as {"code","message"}, each rule with its own message."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.exceptions import RebateRuleError
from app.presentation.errors import register_exception_handlers

CASES = [
    ("bracket_table_empty", 422),
    ("bracket_table_must_start_at_zero", 422),
    ("bracket_table_not_contiguous", 422),
    ("last_bracket_must_be_open", 422),
    ("overlapping_schedules", 409),
    ("schedule_overlaps_existing", 409),
    ("reference_not_found", 422),
    ("revenue_must_not_be_negative", 422),
    ("duplicate_flight_id", 422),
]


def _response(code: str):
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise RebateRuleError(code, "internal detail: schedule 17 of group 4")

    return TestClient(app, raise_server_exceptions=False).get("/boom")


@pytest.mark.parametrize(("code", "status"), CASES)
def test_a_rebate_rule_error_has_its_status_its_code_and_a_fixed_body(code: str, status: int):
    response = _response(code)

    assert response.status_code == status
    assert set(response.json()) == {"code", "message"}
    assert response.json()["code"] == code
    assert "internal detail" not in response.text


def test_every_rule_has_a_different_message():
    messages = [_response(code).json()["message"] for code, _ in CASES]

    assert len(set(messages)) == len(messages)


def test_an_empty_table_and_a_table_that_does_not_start_at_zero_read_differently():
    empty = _response("bracket_table_empty").json()["message"]
    not_from_zero = _response("bracket_table_must_start_at_zero").json()["message"]

    assert empty != not_from_zero
    assert "start at 0" in not_from_zero.lower() or "zero" in not_from_zero.lower()


def test_an_unknown_rule_code_is_still_a_clean_body():
    response = _response("some_future_rule")

    assert response.status_code == 422
    assert set(response.json()) == {"code", "message"}
    assert response.json()["code"] == "some_future_rule"
