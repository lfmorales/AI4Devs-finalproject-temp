import { NO_CATALOGUE_NAME } from "@/features/linking/messages";
import type { ExceptionType, IngestionException } from "@/lib/api/exceptions";

export const TYPE_LABELS: Record<ExceptionType, string> = {
  unmatched_delivery: "Entrega sin emparejar",
  missing_delivery: "Entrega ausente",
  channel_mismatch: "Canal no coincidente",
};

/** Backend error codes of the resolve call, in Spanish. The backend's own text is never shown. */
export const RESOLVE_ERROR_MESSAGES: Record<string, string> = {
  exception_already_resolved: "Esta excepción ya estaba resuelta.",
  exception_not_found: "La excepción ya no existe.",
};

export const RESOLVE_FAILED_MESSAGE = "No se pudo resolver la excepción. Inténtalo de nuevo.";

/** Codes after which the exception is certainly not open any more, so its row leaves the open queue. */
export function leavesTheOpenQueue(code: string | undefined): boolean {
  return code === "exception_already_resolved" || code === "exception_not_found";
}

export function formatDsp(dspId: number | null): string {
  return dspId === null ? "—" : `DSP ${dspId}`;
}

/** The DSP's own campaign and line item; a missing-delivery exception has none, so it names the internal line. */
export function formatExternalPair(row: IngestionException): string {
  if (row.external_campaign_id !== null || row.external_line_item_id !== null) {
    return `${row.external_campaign_id ?? "—"} / ${row.external_line_item_id ?? "—"}`;
  }
  return row.campaign_line_id === null ? "—" : `Línea ${row.campaign_line_id}, periodo ${row.campaign_period_id ?? "—"}`;
}

/** A catalogue name; only a pair from the DSP has one, so the other exception types show a dash. */
export function formatCatalogueName(row: IngestionException, name: string | null): string {
  if (row.exception_type !== "unmatched_delivery") return "—";
  return name ?? NO_CATALOGUE_NAME;
}
