import type { ApiClient } from "./client";

// Shapes of POST /flights/preview, as published by the backend's OpenAPI schema
// (FlightPreviewRequest, FlightPreviewResponse and FlightPreviewFlight).

export interface FlightPreviewRequest {
  /** The line's own dates. Left out when the line inherits the campaign's. */
  start_date?: string;
  end_date?: string;
  campaign_start_date: string;
  campaign_end_date: string;
  contracted_impressions: number;
}

export interface FlightPreviewFlight {
  period_year: number;
  period_month: number;
  flight_start: string;
  flight_end: string;
  contracted_impressions: number;
}

export interface FlightPreviewResponse {
  /** The line's effective dates, own or inherited. */
  start_date: string;
  end_date: string;
  flights: FlightPreviewFlight[];
}

/** Ask the backend how a line's volume would be split into flights. Stores nothing. */
export function previewFlights(client: ApiClient, request: FlightPreviewRequest): Promise<FlightPreviewResponse> {
  return client.post<FlightPreviewResponse>("/flights/preview", request);
}
