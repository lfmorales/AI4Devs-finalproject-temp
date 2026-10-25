import type { ApiClient } from "./client";

// Shapes of the ingestion-exception endpoints, as published by the backend's OpenAPI schema
// (IngestionExceptionResponse and ResolveExceptionRequest). There is no cost field: it is finance-only.

export type ExceptionType = "unmatched_delivery" | "missing_delivery" | "channel_mismatch";
export type ExceptionStatus = "open" | "resolved";

export interface IngestionException {
  id: number;
  exception_type: ExceptionType;
  status: ExceptionStatus;
  ingestion_batch_id: number;
  dsp_id: number | null;
  external_campaign_id: string | null;
  external_line_item_id: string | null;
  campaign_line_id: number | null;
  campaign_period_id: number | null;
  first_date: string | null;
  last_date: string | null;
  days: number;
  impressions_total: number;
  clicks_total: number;
  resolved_at: string | null;
  resolved_by: number | null;
  note: string | null;
}

export function listIngestionExceptions(client: ApiClient, status: ExceptionStatus): Promise<IngestionException[]> {
  return client.get<IngestionException[]>(`/ingestion-exceptions?status=${status}`);
}

/** Marks the exception resolved. Nothing is reprocessed. */
export function resolveIngestionException(
  client: ApiClient,
  exceptionId: number,
  note: string | null,
): Promise<IngestionException> {
  return client.post<IngestionException>(`/ingestion-exceptions/${exceptionId}/resolve`, { note });
}
