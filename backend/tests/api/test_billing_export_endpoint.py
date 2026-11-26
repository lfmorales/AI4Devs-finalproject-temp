"""GET /billing/export: the CSV of a closed month's billing, built only from the closing's snapshots
(finance/billing-report, «A closed month's billing is exported as a CSV»).

October 2026, closed on 2 November. «Alpha» (agency «Alpha agency») contracted 1,000,000 at 5.00 € under the purchase
order OC-2026-001 and delivered 700,000: it bills 3,500.00 €; its line also has a November flight, still open. «Beta»
delivered 700,000 of 1,000,000 and is adjusted to a custom billing of 4,200.00 € with a reason that holds the separator.
«Gamma» is a target line whose DSP reported 4,400.00 € for 1,100,000 served of a target of 1,000,000.
"""

import dataclasses
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.application.services.delivery_ingestion_service import DeliveryIngestionService
from app.domain.services import closed_flight
from app.domain.value_objects.delivery import DeliveryDateRange, ExternalLineKey
from app.infrastructure.persistence.base import Base
from app.infrastructure.persistence.models.campaign import CampaignLinePeriodRecord, CampaignLineRecord, CampaignRecord
from app.infrastructure.persistence.models.purchase_order import PurchaseOrderRecord, PurchaseOrderVersionRecord
from app.infrastructure.persistence.repositories import sqlalchemy_margin_repositories
from app.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from app.presentation.dependencies import providers
from tests.fixtures.delivery_data import (
    campaign_id_of,
    insert_campaign_line,
    insert_delivery,
    insert_ingestion_batch,
    insert_mapping,
    replace_flights,
    seeded_dsp_id,
)
from tests.fixtures.delivery_rows import dsp_row
from tests.fixtures.dsp_delivery_client import InMemoryDspDeliveryClient
from tests.fixtures.margin_data import make_month_closable

OCTOBER = (date(2026, 10, 1), date(2026, 10, 31))
NOVEMBER = (date(2026, 11, 1), date(2026, 11, 30))
AFTER_OCTOBER = date(2026, 11, 2)  # D-1 is 1 November: October has ended, November runs
REASON = "Acuerdo; se factura la OC"
BOM = b"\xef\xbb\xbf"
HEADER = "cliente;agencia;campaña;línea;orden de compra;entregado;contratado;arrastre;facturable;CPM;importe;ajustado;motivo"
ALPHA_ROW = "Alpha advertiser;Alpha agency;Alpha;1;OC-2026-001;700000,0000;1000000;0;700000,0000;5,00;3500,00;no;"
BETA_ROW = f'Beta advertiser;Beta agency;Beta;1;;700000,0000;1000000;0;;5,00;4200,00;sí;"{REASON}"'
GAMMA_ROW = "Gamma advertiser;Gamma agency;Gamma;1;;1100000,0000;1000000;0;;5,00;4400,00;no;"


def _on(client: TestClient, today: date = AFTER_OCTOBER) -> TestClient:
    client.app.dependency_overrides[providers.get_today] = lambda: today
    return client


def _flight_id(session: Session, line_id: int, month: int) -> int:
    return int(session.scalars(
        select(CampaignLinePeriodRecord.id).where(
            CampaignLinePeriodRecord.campaign_line_id == line_id,
            func.extract("month", CampaignLinePeriodRecord.flight_start) == month,
        )
    ).one())


def _october_line(session: Session, name: str, delivered: int, end: date = OCTOBER[1]) -> int:
    line_id = insert_campaign_line(session, name, OCTOBER[0], end)
    replace_flights(session, line_id, [OCTOBER] if end == OCTOBER[1] else [OCTOBER, NOVEMBER])
    insert_delivery(session, line_id, date(2026, 10, 10), delivered, insert_ingestion_batch(session), Decimal("300.00"))
    return line_id


def _under_purchase_order(session: Session, line_id: int, reference: str) -> None:
    order = PurchaseOrderRecord(order_reference=reference, received_on=date(2026, 9, 20))
    session.add(order)
    session.flush()
    version = PurchaseOrderVersionRecord(purchase_order_id=order.id, version_number=1, issued_on=date(2026, 9, 20))
    session.add(version)
    session.flush()
    session.execute(update(CampaignLineRecord).where(CampaignLineRecord.id == line_id).values(
        purchase_order_version_id=version.id))


def _october(session: Session, finance: TestClient) -> dict[str, int]:
    alpha = _october_line(session, "Alpha", 700_000, end=NOVEMBER[1])
    _under_purchase_order(session, alpha, "OC-2026-001")
    beta = _october_line(session, "Beta", 700_000)
    gamma = insert_campaign_line(session, "Gamma", *OCTOBER)
    replace_flights(session, gamma, [OCTOBER])
    session.execute(update(CampaignLineRecord).where(CampaignLineRecord.id == gamma).values(volume_commitment="target"))
    insert_delivery(session, gamma, date(2026, 10, 30), 1_100_000, insert_ingestion_batch(session),
                    reported_revenue=Decimal("4400.00"), buyer_spend=Decimal("5500.00"))
    adjusted = finance.post(f"/billing/flights/{_flight_id(session, beta, 10)}/adjustments",
                            json={"basis": "custom", "amount": "4200.00", "reason": REASON})
    assert adjusted.status_code == 201, adjusted.text
    return {"alpha": alpha, "beta": beta, "gamma": gamma}


def _close_october(session: Session, client: TestClient) -> None:
    make_month_closable(session, 2026, 10, None, AFTER_OCTOBER)
    response = client.post("/margin/closings", json={"year": 2026, "month": 10})
    assert response.status_code == 200, response.text


def _export(client: TestClient, month: int = 10) -> Any:
    return client.get("/billing/export", params={"year": 2026, "month": month})


@pytest.fixture
def finance(client_for_roles: Any) -> TestClient:
    return _on(client_for_roles("finance"))


@pytest.fixture
def closed_october(finance: TestClient, test_db_session: Session) -> dict[str, int]:
    lines = _october(test_db_session, finance)
    _close_october(test_db_session, finance)
    return lines


# ---------------------------------------------------------------- the file


def test_the_file_starts_with_the_byte_order_mark_and_the_header(finance: TestClient, closed_october: dict[str, int]) -> None:
    content = _export(finance).content

    assert content[:3] == b"\xef\xbb\xbf"
    assert content.startswith(BOM + (HEADER + "\r\n").encode("utf-8"))


def test_a_row_carries_its_figures_with_a_decimal_comma_and_no_thousands_separator(
    finance: TestClient, closed_october: dict[str, int]
) -> None:
    lines = _export(finance).content.decode("utf-8-sig").split("\r\n")

    assert lines[1] == ALPHA_ROW
    assert "3500,00" in lines[1] and "700000,0000" in lines[1]
    assert "3500.00" not in lines[1] and "3.500,00" not in lines[1] and "700.000,0000" not in lines[1]


def test_the_whole_file_of_the_closed_month_byte_for_byte(finance: TestClient, closed_october: dict[str, int]) -> None:
    response = _export(finance)

    expected = BOM + "\r\n".join([HEADER, ALPHA_ROW, BETA_ROW, GAMMA_ROW, ""]).encode("utf-8")
    assert response.status_code == 200
    assert response.content == expected


def test_the_file_is_named_after_the_month_and_served_as_utf_8_csv(
    finance: TestClient, closed_october: dict[str, int]
) -> None:
    response = _export(finance)

    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="facturacion-2026-10.csv"'


def test_an_adjusted_flight_carries_its_reason_quoted_because_it_holds_the_separator(
    finance: TestClient, closed_october: dict[str, int]
) -> None:
    rows = _export(finance).content.decode("utf-8-sig").split("\r\n")

    assert rows[2].endswith(';4200,00;sí;"Acuerdo; se factura la OC"')
    assert rows[2].split(";")[8] == ""  # a custom billing has no billable volume


def test_a_target_flight_carries_what_was_reported_and_no_billable_volume(
    finance: TestClient, closed_october: dict[str, int]
) -> None:
    rows = _export(finance).content.decode("utf-8-sig").split("\r\n")

    assert rows[3] == GAMMA_ROW


def test_the_open_november_flight_of_a_closed_line_has_no_row(finance: TestClient, closed_october: dict[str, int]) -> None:
    rows = [row for row in _export(finance).content.decode("utf-8-sig").split("\r\n") if row]

    assert len(rows) == 4 and sum(row.startswith("Alpha advertiser;") for row in rows) == 1


def test_a_flight_closed_before_the_billing_was_frozen_has_no_carry_over_no_billable_volume_and_is_not_adjusted(
    finance: TestClient, test_db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _october_line(test_db_session, "Legacy", 700_000)

    def legacy_snapshot(item: Any) -> Any:  # a snapshot as the closings before committed-billing-and-review wrote it
        return dataclasses.replace(
            closed_flight.snapshot_of(item), billing_basis=None, billable=None, carryover=None, carryover_billable=None,
            billing_adjustment_id=None,
        )

    monkeypatch.setattr(sqlalchemy_margin_repositories, "snapshot_of", legacy_snapshot)
    _close_october(test_db_session, finance)

    (row,) = [row for row in _export(finance).content.decode("utf-8-sig").split("\r\n")[1:] if row]

    assert row == "Legacy advertiser;Legacy agency;Legacy;1;;700000,0000;1000000;;;5,00;3500,00;no;"


def test_every_closing_of_the_month_adds_its_flights(
    finance: TestClient, test_db_session: Session, closed_october: dict[str, int]
) -> None:
    late = _october_line(test_db_session, "Late", 1_000_000)
    _close_october(test_db_session, _on(finance, date(2026, 11, 10)))

    rows = [row for row in _export(finance).content.decode("utf-8-sig").split("\r\n")[1:] if row]

    assert [row.split(";")[2] for row in rows] == ["Alpha", "Beta", "Gamma", "Late"]
    assert late


def test_the_names_are_the_campaign_s_as_stored_now_and_the_figures_the_snapshot_s(
    finance: TestClient, test_db_session: Session, closed_october: dict[str, int]
) -> None:
    alpha = closed_october["alpha"]
    test_db_session.execute(update(CampaignRecord).where(CampaignRecord.id == campaign_id_of(test_db_session, alpha))
                            .values(name="Alpha renamed"))
    test_db_session.execute(update(CampaignLineRecord).where(CampaignLineRecord.id == alpha).values(sale_cpm=Decimal("9.00")))
    test_db_session.flush()

    row = _export(finance).content.decode("utf-8-sig").split("\r\n")[1]

    assert row == ALPHA_ROW.replace(";Alpha;", ";Alpha renamed;")


# ---------------------------------------------------------------- a later delivery does not change it


def test_a_reingestion_of_the_closed_month_leaves_the_file_identical_byte_for_byte(
    finance: TestClient, test_db_session: Session, closed_october: dict[str, int]
) -> None:
    first = _export(finance)
    assert (first.status_code, first.content[:3]) == (200, BOM)
    before = first.content
    rows = []
    for name, line_id in closed_october.items():
        key = ExternalLineKey(f"campaign-{name}", f"line-{name}")
        insert_mapping(test_db_session, line_id, seeded_dsp_id(test_db_session), key.external_campaign_id,
                       key.external_line_item_id)
        # The DSP restates 10 October with twice the impressions and more cost.
        rows.append(dsp_row(date(2026, 10, 10), key, impressions=1_400_000, media_cost=Decimal("900.00")))

    result = DeliveryIngestionService(
        InMemoryDspDeliveryClient(rows), lambda: SqlAlchemyUnitOfWork(lambda: test_db_session),
        lambda: datetime(2026, 11, 3, 2, 0),
    ).run(seeded_dsp_id(test_db_session), date(2026, 11, 3), window=DeliveryDateRange(*OCTOBER))
    after = _export(finance).content

    assert result.stored_row_count == len(rows)
    margin = finance.get("/margin", params={"year": 2026, "month": 10}).json()
    assert any(f["delivery_changed"] for c in margin["campaigns"] for line in c["lines"] for f in line["flights"])
    assert after == before


# ---------------------------------------------------------------- an open month; nothing written; roles


def test_a_month_without_a_closing_has_no_csv(finance: TestClient, test_db_session: Session) -> None:
    _october(test_db_session, finance)

    response = _export(finance)

    assert response.status_code == 409
    assert response.json() == {"code": "month_not_closed", "message": response.json()["message"]}
    assert "2026-10" in response.json()["message"]


def _row_counts(session: Session) -> dict[str, int]:
    return {table.name: int(session.scalar(select(func.count()).select_from(table)) or 0) for table in Base.metadata.sorted_tables}


def test_exporting_writes_nothing(finance: TestClient, test_db_session: Session, closed_october: dict[str, int]) -> None:
    before = _row_counts(test_db_session)

    assert _export(finance).status_code == 200

    assert _row_counts(test_db_session) == before


@pytest.mark.parametrize("params", [{"year": 2026, "month": 13}, {"year": 2026}, {"month": 10}])
def test_a_missing_or_invalid_month_is_a_validation_error(finance: TestClient, params: dict[str, object]) -> None:
    response = finance.get("/billing/export", params=params)

    assert response.status_code == 422 and set(response.json()) == {"code", "message"}


def test_operations_may_export(client_for_roles: Any, test_db_session: Session, closed_october: dict[str, int]) -> None:
    assert _export(_on(client_for_roles("operations"))).status_code == 200


@pytest.mark.parametrize("role", ["trading", "business"])
def test_trading_and_business_are_forbidden(client_for_roles: Any, role: str) -> None:
    response = _export(_on(client_for_roles(role)))

    assert response.status_code == 403 and set(response.json()) == {"code", "message"}
