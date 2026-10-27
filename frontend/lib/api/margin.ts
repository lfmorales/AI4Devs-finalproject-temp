import type { ApiClient } from "./client";
import { buildQuery } from "./query";

// Shapes of GET /margin and POST /margin/closings, as published by the backend's OpenAPI schema
// (MarginResponse, CampaignMarginResponse, LineMarginResponse, FlightMarginResponse, TotalsResponse,
// AppliedRatesResponse, ClosingRequest and ClosingResponse). Every amount, rate and percentage is a decimal
// string: it is displayed as received and never converted to a number.

export type DecimalString = string;

export type FlightState = "closed" | "pending_close" | "running";

export interface MarginTotals {
  revenue: DecimalString;
  media_cost: DecimalString;
  rebate: DecimalString;
  platform_cost: DecimalString;
  margin: DecimalString;
  provisional: boolean;
  flights_counted: number;
  below_cost_count: number;
  zero_sale_count: number;
  /** Computed by the server, in points of revenue; null when there is no revenue. */
  margin_pct: DecimalString | null;
}

export interface AppliedRates {
  platform_rate: DecimalString;
  effective_rebate_rate: DecimalString;
  rebate_step: number;
  agency_exception: boolean;
  zero_reason: string | null;
  source_year: number | null;
}

export interface FlightMargin {
  flight_id: number;
  period_year: number;
  period_month: number;
  flight_start: string;
  flight_end: string;
  state: FlightState;
  provisional: boolean;
  /** A negative final margin ("Margen negativo"). */
  below_cost: boolean;
  /** A line without a price ("Sin venta"). */
  zero_sale: boolean;
  revenue: DecimalString;
  media_cost: DecimalString;
  rebate: DecimalString;
  platform_cost: DecimalString;
  margin: DecimalString;
  margin_pct: DecimalString | null;
  rates: AppliedRates;
}

export interface LineMargin {
  campaign_line_id: number;
  line_number: number;
  channel: string;
  scope: string;
  zero_sale: boolean;
  flights: FlightMargin[];
  totals: MarginTotals;
}

export interface CampaignMargin {
  campaign_id: number;
  name: string;
  status: string;
  zero_sale: boolean;
  lines: LineMargin[];
  totals: MarginTotals;
}

export interface MarginResponse {
  as_of: string;
  campaigns: CampaignMargin[];
  totals: MarginTotals;
}

export interface MarginFilters {
  year?: number;
  month?: number;
  campaignId?: number;
}

export interface ClosingRequest {
  year: number;
  month: number;
}

export interface ClosingResponse {
  year: number;
  month: number;
  closed: number;
  already_closed: number;
}

export function marginPath(filters: MarginFilters): string {
  return `/margin${buildQuery({ year: filters.year, month: filters.month, campaign_id: filters.campaignId })}`;
}

export function getMargin(client: ApiClient, filters: MarginFilters): Promise<MarginResponse> {
  return client.get<MarginResponse>(marginPath(filters));
}

/** Freezes the rates of the flights that ended in a month. Idempotent on the server. */
export function closeMonth(client: ApiClient, request: ClosingRequest): Promise<ClosingResponse> {
  return client.post<ClosingResponse>("/margin/closings", request);
}
