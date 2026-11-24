"""Neither the Equativ client secret nor its access token reaches the logs, an error message or a repr."""

import logging
import traceback
from datetime import date

import httpx
import pytest

from app.domain.exceptions import DomainError
from app.domain.value_objects.delivery import DeliveryDateRange
from app.infrastructure.dsp.equativ_delivery_client import EquativDeliveryClient
from tests.fixtures.fake_equativ import TOKEN_VALUE, FakeEquativ, package_row

SECRET = "synthetic-equativ-secret-0123456789"
CLIENT_ID = "synthetic-equativ-client-id"
WINDOW = DeliveryDateRange(date(2026, 11, 17), date(2026, 11, 23))
# A server that echoes what it was sent in its error body is the worst case for a client that copies bodies.
ECHOING_BODY = f'{{"title": "denied", "detail": "{SECRET} {TOKEN_VALUE}"}}'
SENSITIVE_VALUES = [SECRET, TOKEN_VALUE]


@pytest.fixture(autouse=True)
def _logging_enabled(caplog: pytest.LogCaptureFixture) -> None:
    """Alembic's fileConfig, run when the test database is migrated, disables loggers created before it.

    Without this the log assertions below would pass vacuously because nothing is captured.
    """
    for name in ("app.infrastructure.dsp.equativ_delivery_client", "httpx"):
        logging.getLogger(name).disabled = False
    caplog.set_level(logging.DEBUG)


def _client(fake: FakeEquativ) -> EquativDeliveryClient:
    return EquativDeliveryClient(CLIENT_ID, SECRET, fake.client(), sleep=lambda _: None, monotonic=lambda: 0.0)


def _assert_nothing_sensitive(text: str) -> None:
    for value in SENSITIVE_VALUES:
        assert value not in text


def _all_logs(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(f"{record.name} {record.getMessage()} {record.args}" for record in caplog.records)


def test_a_successful_run_logs_no_secret_or_token(caplog: pytest.LogCaptureFixture) -> None:
    list(_client(FakeEquativ(rows=[package_row()])).fetch_delivery(WINDOW))

    assert caplog.records, "the run is expected to log its progress"
    _assert_nothing_sensitive(_all_logs(caplog))


@pytest.mark.parametrize(
    "fake",
    [
        FakeEquativ(token_status=401, error_body=ECHOING_BODY),
        FakeEquativ(token_status=500, error_body=ECHOING_BODY),
        FakeEquativ(create_status=403, error_body=ECHOING_BODY),
        FakeEquativ(create_status=500, error_body=ECHOING_BODY),
        FakeEquativ(statuses=["ReportGenerationFailed"]),
        FakeEquativ(fail_with=httpx.ConnectError(f"cannot reach with {SECRET}")),
    ],
    ids=["token-401", "token-500", "create-403", "create-500", "failed-report", "unreachable"],
)
def test_a_failure_exposes_no_secret_or_token_in_the_error_or_the_logs(
    fake: FakeEquativ, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(DomainError) as failure:
        list(_client(fake).fetch_delivery(WINDOW))

    rendered = "".join(traceback.format_exception(failure.value)) + str(failure.value) + _all_logs(caplog)
    _assert_nothing_sensitive(rendered)


def test_the_repr_of_the_client_carries_no_secret_or_token() -> None:
    client = _client(FakeEquativ(rows=[package_row()]))
    list(client.fetch_delivery(WINDOW))

    _assert_nothing_sensitive(repr(client) + str(client))
