import type { DeliveryMetric } from "@/lib/format/delivery-metric";

import type { ApiClient, DownloadedFile } from "./client";
import type { BillingBasis, DecimalString } from "./margin";
import { buildQuery } from "./query";

// Shapes of the /billing routes, as published by the backend's OpenAPI schema (BillingResponse,
// BillingCampaignResponse, BillingLineResponse, BillingFlightResponse and BillingAdjustmentInForce). Every amount and
// volume with decimals is a decimal string: it is displayed as received and never converted to a number.

export type ReviewState = "in_progress" | "pending_review" | "reviewed" | "closed";

export type BillingFlightState = "not_started" | "running" | "pending_close" | "closed";

export interface AdjustmentInForce {
  basis: AdjustmentBasis;
  /** Only with `custom`, two decimals. */
  amount: DecimalString | null;
  reason: string;
  created_by: number;
  created_at: string;
}

export interface BillingFlight {
  flight_id: number;
  flight_start: string;
  flight_end: string;
  state: BillingFlightState;
  delivery_metric: DeliveryMetric;
  /** In the unit of `delivery_metric`, as every volume of the flight. */
  contracted_impressions: number;
  /** Null for a flight closed before the billing was frozen. */
  carryover: number | null;
  carryover_billable: boolean | null;
  delivery_target: number;
  /** Four decimals; null for a flight not started. */
  delivered: string | null;
  /** Four decimals; null for a flight not started, a target flight and a custom billing. */
  billable: string | null;
  /** GET /margin's `revenue`; null for a flight not started. */
  billing: DecimalString | null;
  billing_basis: BillingBasis | null;
  sale_cpm: DecimalString;
  adjustment: AdjustmentInForce | null;
}

export interface BillingLine {
  campaign_line_id: number;
  line_number: number;
  flights: BillingFlight[];
}

export interface BillingCampaign {
  campaign_id: number;
  name: string;
  agency: string;
  advertiser: string;
  review_state: ReviewState;
  /** Who wrote the latest review event of the month, and when; null when there is none. */
  review_set_by: number | null;
  review_set_at: string | null;
  lines: BillingLine[];
}

export interface BillingResponse {
  year: number;
  month: number;
  as_of: string;
  campaigns: BillingCampaign[];
}

export interface BillingMonth {
  year: number;
  month: number;
}

export function billingPath(month: BillingMonth): string {
  return `/billing${buildQuery({ year: month.year, month: month.month })}`;
}

export function getBilling(client: ApiClient, month: BillingMonth): Promise<BillingResponse> {
  return client.get<BillingResponse>(billingPath(month));
}

export interface ReviewRequest {
  campaign_id: number;
  year: number;
  month: number;
}

export interface ReviewResponse extends ReviewRequest {
  state: "reviewed" | "pending_review";
  set_by: number;
  set_at: string;
}

/** Marks a campaign reviewed in a month; one already reviewed answers its current review. */
export function reviewCampaign(client: ApiClient, request: ReviewRequest): Promise<ReviewResponse> {
  return client.post<ReviewResponse>("/billing/reviews", request);
}

/** Withdraws the review: the campaign goes back to pending review, and the withdrawal stays in its history. */
export function withdrawReview(client: ApiClient, request: ReviewRequest): Promise<ReviewResponse> {
  return client.post<ReviewResponse>("/billing/reviews/withdrawals", request);
}

export type AdjustmentBasis = "minimum" | "delivered" | "contracted" | "custom";

export interface AdjustmentRequest {
  basis: AdjustmentBasis;
  /** Only with `custom`: a decimal string with at most two decimals. */
  amount: DecimalString | null;
  reason: string;
}

export interface AdjustmentItem {
  id: number;
  flight_id: number;
  basis: AdjustmentBasis;
  amount: DecimalString | null;
  reason: string;
  created_by: number;
  created_at: string;
}

export interface AdjustmentResponse extends AdjustmentItem {
  /** What the flight bills after the adjustment, by the server. */
  billing: DecimalString;
}

export interface HistoryItem extends AdjustmentItem {
  in_force: boolean;
}

export function adjustFlight(client: ApiClient, flightId: number, request: AdjustmentRequest): Promise<AdjustmentResponse> {
  return client.post<AdjustmentResponse>(`/billing/flights/${flightId}/adjustments`, request);
}

/** Every adjustment of a flight, latest first; the first is the one in force. */
export async function adjustmentHistory(client: ApiClient, flightId: number): Promise<HistoryItem[]> {
  return (await client.get<{ adjustments: HistoryItem[] }>(`/billing/flights/${flightId}/adjustments`)).adjustments;
}

export interface BillableResponse {
  flight_id: number;
  carryover: number;
  billable: boolean;
  set_by: number;
  set_at: string;
}

/** Decides whether a flight's carry-over raises the cap of its billing. The volume does not change. */
export function setCarryoverBillable(client: ApiClient, flightId: number, billable: boolean): Promise<BillableResponse> {
  return client.put<BillableResponse>(`/billing/flights/${flightId}/carryover/billable`, { billable });
}

/** The name the server gives the CSV of a month, when its answer does not carry one. */
export function exportFileName(month: BillingMonth): string {
  return `facturacion-${month.year}-${month.month < 10 ? "0" : ""}${month.month}.csv`;
}

/** The CSV of a closed month, built by the server from the closing's snapshots. */
export function downloadExport(client: ApiClient, month: BillingMonth): Promise<DownloadedFile> {
  return client.getFile(`/billing/export${buildQuery({ year: month.year, month: month.month })}`);
}
