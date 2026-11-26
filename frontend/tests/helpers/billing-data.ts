/** Builders of GET /billing responses, shaped as the backend's OpenAPI schema (BillingResponse and its parts). */
import type {
  AdjustmentInForce,
  BillingCampaign,
  BillingFlight,
  BillingLine,
  BillingResponse,
} from "@/lib/api/billing";

/** A pending-close committed flight of 1,000,000 contracted at 5.00 € that delivered 700,000 and bills 3,500.00 €. */
export function billingFlight(overrides: Partial<BillingFlight> = {}): BillingFlight {
  return {
    flight_id: 31,
    flight_start: "2026-10-01",
    flight_end: "2026-10-31",
    state: "pending_close",
    delivery_metric: "impressions",
    contracted_impressions: 1000000,
    carryover: 0,
    carryover_billable: false,
    delivery_target: 1000000,
    delivered: "700000.0000",
    billable: "700000.0000",
    billing: "3500.00",
    billing_basis: "minimum",
    sale_cpm: "5.00",
    adjustment: null,
    ...overrides,
  };
}

export function adjustmentInForce(overrides: Partial<AdjustmentInForce> = {}): AdjustmentInForce {
  return {
    basis: "custom",
    amount: "4200.00",
    reason: "Acuerdo con la agencia",
    created_by: 7,
    created_by_name: "Ana Pérez",
    created_at: "2026-11-02T10:15:30.123456",
    ...overrides,
  };
}

export function billingLine(overrides: Partial<BillingLine> = {}): BillingLine {
  return { campaign_line_id: 11, line_number: 1, flights: [billingFlight()], ...overrides };
}

export function billingCampaign(overrides: Partial<BillingCampaign> = {}): BillingCampaign {
  return {
    campaign_id: 1,
    name: "Alfa",
    agency: "Agencia Uno",
    advertiser: "Anunciante Uno",
    review_state: "pending_review",
    review_set_by: null,
    review_set_by_name: null,
    review_set_at: null,
    lines: [billingLine()],
    ...overrides,
  };
}

export function billing(overrides: Partial<BillingResponse> = {}): BillingResponse {
  return { year: 2026, month: 10, as_of: "2026-11-01", campaigns: [billingCampaign()], ...overrides };
}
