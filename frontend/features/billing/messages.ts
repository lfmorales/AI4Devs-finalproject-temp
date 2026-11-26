import type { AdjustmentBasis, BillingFlightState, BillingMonth, ReviewState } from "@/lib/api/billing";
import { monthOfYear } from "@/features/margin/messages";

export const REVIEW_STATE_LABEL: Record<ReviewState, string> = {
  in_progress: "En curso",
  pending_review: "Pendiente de revisión",
  reviewed: "Revisada",
  closed: "Cerrada",
};

export const REVIEW_STATE_CLASS: Record<ReviewState, string> = {
  in_progress: "tag tag-info",
  pending_review: "tag tag-warning",
  reviewed: "tag",
  closed: "tag",
};

export const FLIGHT_STATE_LABEL: Record<BillingFlightState, string> = {
  not_started: "Sin empezar",
  running: "En curso",
  pending_close: "Pendiente de cierre",
  closed: "Cerrado",
};

/** The bases of an adjustment, as the form offers them and the history names them. */
export const BASIS_LABEL: Record<AdjustmentBasis, string> = {
  minimum: "Regla del mínimo",
  delivered: "Todo lo entregado",
  contracted: "Lo contratado (el tope)",
  custom: "Importe fijo",
};

export const BASIS_ORDER: readonly AdjustmentBasis[] = ["minimum", "delivered", "contracted", "custom"];

export const CHOOSE_MONTH = "Elige año y mes para ver la facturación";
export const CSV_NEEDS_A_CLOSED_MONTH = "El CSV está disponible cuando el mes está cerrado";
export const NO_ADJUSTMENTS = "Este flight no tiene ajustes";

/** «por el usuario 7 el 02/11/2026 10:15»: who and when, as the server sent them. */
export function byUserAt(userId: number, moment: string): string {
  return `por el usuario ${userId} el ${moment}`;
}

export const GENERIC_ERROR = "No se pudo completar la acción. Inténtalo de nuevo más tarde.";

// The Spanish text of every code the billing routes answer, with what to do. The backend's own text is never shown.
const MESSAGE_BY_CODE: Record<string, string> = {
  invalid_adjustment:
    "El ajuste no es válido: elige una base, escribe el motivo y, solo con un importe fijo, un importe de cero o más con dos decimales como máximo.",
  flight_not_ended: "Este flight aún no ha terminado: se podrá ajustar cuando acabe.",
  flight_closed:
    "El mes de este flight ya está cerrado: su facturación no se puede ajustar. Recarga la página para ver lo que se congeló.",
  flight_not_found: "Este flight ya no existe. Recarga la página.",
  campaign_not_found: "La campaña ya no existe. Recarga la página.",
  campaign_month_not_found: "La campaña no tiene flights en este mes. Recarga la página.",
  campaign_month_in_progress: "La campaña tiene flights en curso este mes: se podrá revisar cuando terminen.",
  campaign_month_closed: "El mes de esta campaña ya está cerrado: su revisión no se puede cambiar.",
  not_reviewed: "La campaña no está revisada: no hay revisión que quitar. Recarga la página.",
  no_carryover: "Este flight no tiene arrastre que facturar. Recarga la página.",
  month_closed: "El mes de este flight ya está cerrado: la marca del arrastre no se puede cambiar.",
  validation_error: "La petición no es válida: revisa los datos e inténtalo de nuevo.",
};

/** What the backend names when a DSP has not loaded the month's last day: "... of 2026-10 from Adform is not ...". */
const NOT_LOADED_DSP = /\d{4}-\d{2} from (.+?) is not loaded/;

export interface ErrorContext {
  month: BillingMonth;
  /** The campaign the action was on, when it was on one. */
  campaign?: string;
}

/** The Spanish message of a refused action, from the backend's code; `message` is only read for the DSP. */
export function billingErrorMessage(code: string | undefined, message: string | undefined, context: ErrorContext): string {
  const month = monthOfYear(context.month.year, context.month.month);
  if (code === "month_delivery_not_loaded") {
    const match = message === undefined ? null : NOT_LOADED_DSP.exec(message);
    const who = match === null ? "el DSP" : (match[1] ?? "el DSP");
    return `No se puede revisar ${context.campaign ?? "la campaña"}: ${who} aún no ha cargado la entrega del último día `
      + `de ${month}. Espera a la ingesta de ese día y vuelve a marcarla como revisada.`;
  }
  if (code === "month_not_closed") return `${month} no está cerrado: el CSV se puede descargar cuando se cierre el mes.`;
  if (code !== undefined && code in MESSAGE_BY_CODE) return MESSAGE_BY_CODE[code] ?? GENERIC_ERROR;
  return GENERIC_ERROR;
}
