import type { ApiClient } from "./client";

// Shapes of GET /campaign-status, as published by the backend's OpenAPI schema
// (CampaignStatusResponse, NamedReference, FlightWindowResponse and PacingResponse).
// The response deliberately has no cost or margin field.

export interface NamedReference {
  id: number;
  name: string;
}

export interface FlightWindow {
  campaign_period_id: number;
  year: number;
  month: number;
  start: string;
  end: string;
}

export type PacingStatus = "on_pace" | "under_delivering" | "over_delivering";

export interface Pacing {
  expected_impressions: number;
  /** A fraction (-0.2 is 20% under the expected delivery); null when nothing was expected yet. */
  deviation: number | null;
  days_remaining: number;
  status: PacingStatus;
}

/** One running flight of an active campaign. */
export interface CampaignStatusRow {
  campaign: NamedReference;
  agency: NamedReference;
  line_number: number;
  flight: FlightWindow;
  contracted_impressions: number;
  delivered_impressions: number;
  /** Delivered over contracted, as a fraction; null when it cannot be computed. */
  delivery_ratio: number | null;
  pacing: Pacing;
  pacing_flag: boolean;
  missing_data_flag: boolean;
}

/** The daily status, already ordered by the server (rows with a flag first). */
export function getCampaignStatus(client: ApiClient): Promise<CampaignStatusRow[]> {
  return client.get<CampaignStatusRow[]>("/campaign-status");
}
