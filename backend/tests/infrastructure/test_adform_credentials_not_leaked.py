"""Neither the client secret nor an access token reaches the logs, an error message or a repr."""

import base64
import logging
import traceback
from datetime import date

import pytest

from app.domain.exceptions import DomainError
from app.domain.value_objects.delivery import DeliveryDateRange
from app.infrastructure.dsp.adform_delivery_client import AdformDeliveryClient
from tests.fixtures.fake_adform import TOKEN_VALUE, FakeAdform, report_row

SECRET = "synthetic-client-secret-0123456789"
CLIENT_ID = "synthetic-client-id"
BASIC_CREDENTIALS = base64.b64encode(f"{CLIENT_ID}:{SECRET}".encode()).decode()
RANGE = DeliveryDateRange(date(2026, 8, 3), date(2026, 8, 9))
# A server that echoes what it was sent in its error body is the worst case for a client that copies bodies.
ECHOING_BODY = f'{{"error": "denied", "echo": "{SECRET} {TOKEN_VALUE} {BASIC_CREDENTIALS}"}}'
SENSITIVE_VALUES = [SECRET, TOKEN_VALUE, BASIC_CREDENTIALS]


@pytest.fixture(autouse=True)
def _logging_enabled(caplog):
    """Alembic's fileConfig, run when the test database is migrated, disables loggers created before it.

    Without this the log assertions below would pass vacuously because nothing is captured.
    """
    for name in ("app.infrastructure.dsp.adform_delivery_client", "httpx"):
        logging.getLogger(name).disabled = False
    caplog.set_level(logging.DEBUG)


def _client(fake: FakeAdform) -> AdformDeliveryClient:
    return AdformDeliveryClient(CLIENT_ID, SECRET, fake.client(), sleep=lambda _: None, today=lambda: date(2026, 8, 10))


def _assert_nothing_sensitive(text: str) -> None:
    for value in SENSITIVE_VALUES:
        assert value not in text


def _all_logs(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(f"{record.name} {record.getMessage()} {record.args}" for record in caplog.records)


def test_a_successful_run_logs_no_credential_or_token(caplog):
    list(_client(FakeAdform(rows=[report_row()], statuses=["running", "succeeded"])).fetch_delivery(RANGE))

    assert caplog.records, "the run is expected to log its progress"
    _assert_nothing_sensitive(_all_logs(caplog))


@pytest.mark.parametrize(
    "fake",
    [
        FakeAdform(token_status=401, error_body=ECHOING_BODY),
        FakeAdform(token_status=500, error_body=ECHOING_BODY),
        FakeAdform(data_status=401, error_body=ECHOING_BODY),
        FakeAdform(data_status=500, error_body=ECHOING_BODY),
    ],
    ids=["token-401", "token-500", "data-401", "data-500"],
)
def test_a_failure_exposes_no_credential_or_token_in_the_error_or_the_logs(fake, caplog):
    with pytest.raises(DomainError) as failure:
        list(_client(fake).fetch_delivery(RANGE))

    rendered = "".join(traceback.format_exception(failure.value)) + str(failure.value) + _all_logs(caplog)
    _assert_nothing_sensitive(rendered)


def test_a_failing_token_request_leaves_the_log_free_of_the_secret(caplog):
    fake = FakeAdform(token_status=401, error_body=ECHOING_BODY)

    with pytest.raises(DomainError):
        list(_client(fake).fetch_delivery(RANGE))

    _assert_nothing_sensitive(_all_logs(caplog))


def test_the_client_representation_does_not_show_the_secret():
    client = _client(FakeAdform())

    _assert_nothing_sensitive(repr(client) + str(client) + repr(vars(client)))
