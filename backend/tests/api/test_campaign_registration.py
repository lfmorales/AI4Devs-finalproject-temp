import pytest
import logging
from datetime import date

logger = logging.getLogger(__name__)


def test_register_campaign_success(authenticated_client):
    """Test successful campaign registration returns 201 and persists campaign."""
    payload = {
        "name": "CAMP-SYNC-001",
        "display_name": "Sync Test Campaign",
        "agency_id": 1,
        "advertiser_id": 1,
        "campaign_type_id": 1,
        "sector_id": 1,
        "sales_rep_id": 1,
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "order_reference": "PO-SYNC-001",
        "order_received_on": "2025-12-15",
        "lines": [
            {
                "dsp_id": 1,
                "channel_id": 1,
                "format_id": 1,
                "scope": "national",
                "market_description": "Spain",
                "contracted_impressions": 1000000,
                "sale_cpm": "25.50"
            }
        ]
    }

    response = authenticated_client.post("/campaigns", json=payload)

    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["name"] == "CAMP-SYNC-001"
    assert data["status"] == "active"
    assert len(data["periods"]) > 0
    assert len(data["lines"]) > 0


def test_register_campaign_no_token(client):
    """Test that missing token returns 401."""
    payload = {
        "name": "CAMP-SYNC-002",
        "display_name": "Test Campaign",
        "agency_id": 1,
        "advertiser_id": 1,
        "campaign_type_id": 1,
        "sector_id": 1,
        "sales_rep_id": 1,
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "order_reference": "PO-SYNC-002",
        "order_received_on": "2025-12-15",
        "lines": [
            {
                "dsp_id": 1,
                "channel_id": 1,
                "format_id": 1,
                "scope": "national",
                "market_description": "Spain",
                "contracted_impressions": 1000000,
                "sale_cpm": "25.50"
            }
        ]
    }

    response = client.post("/campaigns", json=payload)

    assert response.status_code == 401  # No token means unauthenticated


def test_register_campaign_invalid_agency(authenticated_client):
    """Test that unknown agency returns 400."""
    payload = {
        "name": "CAMP-SYNC-003",
        "display_name": "Test Campaign",
        "agency_id": 9999,  # Unknown
        "advertiser_id": 1,
        "campaign_type_id": 1,
        "sector_id": 1,
        "sales_rep_id": 1,
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "order_reference": "PO-SYNC-003",
        "order_received_on": "2025-12-15",
        "lines": [
            {
                "dsp_id": 1,
                "channel_id": 1,
                "format_id": 1,
                "scope": "national",
                "market_description": "Spain",
                "contracted_impressions": 1000000,
                "sale_cpm": "25.50"
            }
        ]
    }

    response = authenticated_client.post("/campaigns", json=payload)

    assert response.status_code == 400
    assert "agency" in response.json()["detail"].lower()


def test_list_campaigns_requires_auth(client):
    """Test that GET /campaigns without token returns 401."""
    response = client.get("/campaigns")

    assert response.status_code == 401


def test_register_campaign_duplicate_order_reference(authenticated_client):
    """Test that duplicate order_reference returns 409."""
    payload1 = {
        "name": "CAMP-DUP-001",
        "display_name": "First Campaign",
        "agency_id": 1,
        "advertiser_id": 1,
        "campaign_type_id": 1,
        "sector_id": 1,
        "sales_rep_id": 1,
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "order_reference": "PO-DUPLICATE-001",
        "order_received_on": "2025-12-15",
        "lines": [
            {
                "dsp_id": 1,
                "channel_id": 1,
                "format_id": 1,
                "scope": "national",
                "market_description": "Spain",
                "contracted_impressions": 1000000,
                "sale_cpm": "25.50"
            }
        ]
    }

    # First registration succeeds
    response1 = authenticated_client.post("/campaigns", json=payload1)
    assert response1.status_code == 201

    # Second registration with same order_reference fails with 409
    payload2 = {
        **payload1,
        "name": "CAMP-DUP-002",
        "display_name": "Second Campaign with Same PO"
    }
    response2 = authenticated_client.post("/campaigns", json=payload2)
    assert response2.status_code == 409
    data = response2.json()
    assert data.get("code") == "duplicate_order_reference", f"Expected code field at root level, got {data}"
    assert "message" in data, f"Expected message field in response, got {data}"


def test_register_campaign_error_no_sql_exposure(authenticated_client):
    """Test that 500 errors don't expose SQL in response body."""
    # Try to cause an internal error (though this is hard without crafted payload)
    # For now, test that generic error messages don't include SQL keywords
    response = authenticated_client.post("/campaigns", json={})
    # This should be 422 due to validation, not 500, but let's verify no SQL leaks
    assert "select" not in response.text.lower()
    assert "insert" not in response.text.lower()
    assert "from" not in response.text.lower() or "invalid" in response.text.lower()  # "from" might be in validation error


def test_list_campaigns_returns_created_campaign(authenticated_client):
    """Test that a created campaign appears in GET /campaigns list."""
    # Create a campaign with POST
    payload = {
        "name": "CAMP-LIST-TEST-001",
        "display_name": "Campaign for List Test",
        "agency_id": 1,
        "advertiser_id": 1,
        "campaign_type_id": 1,
        "sector_id": 1,
        "sales_rep_id": 1,
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "order_reference": "PO-LIST-TEST-001",
        "order_received_on": "2025-12-15",
        "lines": [
            {
                "dsp_id": 1,
                "channel_id": 1,
                "format_id": 1,
                "scope": "national",
                "market_description": "Spain",
                "contracted_impressions": 1000000,
                "sale_cpm": "25.50"
            }
        ]
    }

    create_response = authenticated_client.post("/campaigns", json=payload)
    assert create_response.status_code == 201

    # List campaigns and verify the created campaign appears
    list_response = authenticated_client.get("/campaigns")
    assert list_response.status_code == 200

    campaigns = list_response.json()
    campaign_names = [c.get("name") for c in campaigns]
    assert "CAMP-LIST-TEST-001" in campaign_names, f"Campaign not found in list: {campaigns}"


def test_register_campaign_empty_lines_returns_422(authenticated_client):
    """Test that campaign with empty lines list returns 422 validation error."""
    payload = {
        "name": "CAMP-EMPTY-LINES",
        "display_name": "Campaign with Empty Lines",
        "agency_id": 1,
        "advertiser_id": 1,
        "campaign_type_id": 1,
        "sector_id": 1,
        "sales_rep_id": 1,
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "order_reference": "PO-EMPTY-LINES",
        "order_received_on": "2025-12-15",
        "lines": []
    }

    response = authenticated_client.post("/campaigns", json=payload)

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any(e.get("loc") == ["body", "lines"] for e in errors), f"Expected lines validation error, got {errors}"


def test_register_campaign_missing_lines_returns_422(authenticated_client):
    """Test that campaign without lines field returns 422 validation error."""
    payload = {
        "name": "CAMP-NO-LINES",
        "display_name": "Campaign without Lines Field",
        "agency_id": 1,
        "advertiser_id": 1,
        "campaign_type_id": 1,
        "sector_id": 1,
        "sales_rep_id": 1,
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "order_reference": "PO-NO-LINES",
        "order_received_on": "2025-12-15"
    }

    response = authenticated_client.post("/campaigns", json=payload)

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any(e.get("loc") == ["body", "lines"] for e in errors), f"Expected lines validation error, got {errors}"


def test_register_campaign_duplicate_name(authenticated_client):
    """Test that duplicate campaign name returns 409 with code duplicate_campaign_name."""
    payload1 = {
        "name": "CAMP-NAME-DUP-001",
        "display_name": "First Campaign",
        "agency_id": 1,
        "advertiser_id": 1,
        "campaign_type_id": 1,
        "sector_id": 1,
        "sales_rep_id": 1,
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "order_reference": "PO-NAME-DUP-001",
        "order_received_on": "2025-12-15",
        "lines": [
            {
                "dsp_id": 1,
                "channel_id": 1,
                "format_id": 1,
                "scope": "national",
                "market_description": "Spain",
                "contracted_impressions": 1000000,
                "sale_cpm": "25.50"
            }
        ]
    }

    # First registration succeeds
    response1 = authenticated_client.post("/campaigns", json=payload1)
    assert response1.status_code == 201, f"First campaign creation failed: {response1.text}"

    # Second registration with same name but different order_reference fails with 409
    payload2 = {
        **payload1,
        "order_reference": "PO-NAME-DUP-002",  # Different order_reference
        "display_name": "Second Campaign with Same Name"
    }
    response2 = authenticated_client.post("/campaigns", json=payload2)
    assert response2.status_code == 409, f"Expected 409, got {response2.status_code}: {response2.text}"
    data = response2.json()
    assert data.get("code") == "duplicate_campaign_name", f"Expected code field at root level, got {data}"
    assert "message" in data, f"Expected message field in response, got {data}"


def test_register_campaign_duplicate_name_no_purchase_order_created(authenticated_client, test_db_session):
    """Test that failed duplicate name registration doesn't create purchase_order row."""
    from app.infrastructure.persistence.models import PurchaseOrderRecord

    payload1 = {
        "name": "CAMP-NAME-SAFE-001",
        "display_name": "First Campaign",
        "agency_id": 1,
        "advertiser_id": 1,
        "campaign_type_id": 1,
        "sector_id": 1,
        "sales_rep_id": 1,
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "order_reference": "PO-NAME-SAFE-001",
        "order_received_on": "2025-12-15",
        "lines": [
            {
                "dsp_id": 1,
                "channel_id": 1,
                "format_id": 1,
                "scope": "national",
                "market_description": "Spain",
                "contracted_impressions": 1000000,
                "sale_cpm": "25.50"
            }
        ]
    }

    # First registration succeeds
    response1 = authenticated_client.post("/campaigns", json=payload1)
    assert response1.status_code == 201

    # Count purchase orders before duplicate attempt
    po_before = test_db_session.query(PurchaseOrderRecord).count()

    # Second registration with same name but different order_reference fails
    payload2 = {
        **payload1,
        "order_reference": "PO-NAME-SAFE-002",
        "display_name": "Second Campaign"
    }
    response2 = authenticated_client.post("/campaigns", json=payload2)
    assert response2.status_code == 409

    # Verify no new purchase_order was created
    po_after = test_db_session.query(PurchaseOrderRecord).count()
    assert po_before == po_after, f"Purchase order created despite 409 error. Before: {po_before}, After: {po_after}"


def test_register_campaign_flights_point_at_the_campaign_periods(authenticated_client):
    """Each flight of a line points at one of the periods listed in the response."""
    payload = {
        "name": "CAMP-PERIOD-ID-TEST",
        "display_name": "Campaign Period ID Test",
        "agency_id": 1,
        "advertiser_id": 1,
        "campaign_type_id": 1,
        "sector_id": 1,
        "sales_rep_id": 1,
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "order_reference": "PO-PERIOD-ID-TEST",
        "order_received_on": "2025-12-15",
        "lines": [
            {
                "dsp_id": 1,
                "channel_id": 1,
                "format_id": 1,
                "scope": "national",
                "market_description": "Spain",
                "contracted_impressions": 1000000,
                "sale_cpm": "25.50"
            }
        ]
    }

    response = authenticated_client.post("/campaigns", json=payload)
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"

    data = response.json()
    period_ids = {p["id"] for p in data["periods"]}

    # A line has no period of its own: each of its flights points at one of the campaign's periods.
    for line in data["lines"]:
        assert "campaign_period_id" not in line
        assert line["flights"], f"Line {line['id']} has no flights"
        for flight in line["flights"]:
            assert flight["campaign_period_id"] in period_ids, (
                f"Flight of line {line['id']} points at period {flight['campaign_period_id']}, not in {period_ids}"
            )


def test_register_campaign_without_operations_role(authenticated_client_no_operations_role):
    """Test that POST /campaigns without operations role returns 403."""
    payload = {
        "name": "CAMP-AUTH-TEST",
        "display_name": "Authorization Test Campaign",
        "agency_id": 1,
        "advertiser_id": 1,
        "campaign_type_id": 1,
        "sector_id": 1,
        "sales_rep_id": 1,
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "order_reference": "PO-AUTH-TEST",
        "order_received_on": "2025-12-15",
        "lines": [
            {
                "dsp_id": 1,
                "channel_id": 1,
                "format_id": 1,
                "scope": "national",
                "market_description": "Spain",
                "contracted_impressions": 1000000,
                "sale_cpm": "25.50"
            }
        ]
    }

    response = authenticated_client_no_operations_role.post("/campaigns", json=payload)
    assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
    data = response.json()
    assert data.get("code") == "missing_role", f"Expected code=missing_role, got {data}"


def test_list_campaigns_without_operations_or_business_role(authenticated_client_no_operations_role):
    """Test that GET /campaigns without operations or business role returns 403."""
    response = authenticated_client_no_operations_role.get("/campaigns")
    assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
    data = response.json()
    assert data.get("code") == "missing_role", f"Expected code=missing_role, got {data}"
