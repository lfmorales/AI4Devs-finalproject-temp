import { formatInteger } from "@/lib/format/integer";
const MONTH_NAMES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];
const MONTH_CODES = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"];

/** The name of month 1 to 12, in Spanish. */
export function monthName(month: number): string {
  return MONTH_NAMES[month - 1] ?? "";
}

export function monthNames(): readonly string[] {
  return MONTH_NAMES;
}

/** "agosto de 2026". */
export function monthOfYear(year: number | string, month: number): string {
  return `${monthName(month)} de ${year}`;
}

export const GENERIC_CLOSING_ERROR = "No se pudo cerrar el mes. Inténtalo de nuevo más tarde.";

/** What the backend names when an earlier month blocks the closing: "... 2026-06 ...". */
const BLOCKING_MONTH = /(\d{4})-(\d{2})/;

export interface ClosingTarget {
  year: number;
  month: number;
}

// The Spanish text of every code the backend defines for the margin routes. The backend's own text is never shown.
const MESSAGE_BY_CODE: Record<string, string> = {
  validation_error: "La petición no es válida: revisa el año y el mes elegidos.",
  campaign_not_found: "La campaña elegida no existe.",
  platform_rate_not_configured: "No hay una tasa de plataforma de sistema configurada. Contacta con el administrador.",
  identity_provider_unavailable: "No se pudo verificar tu identidad en este momento. Inténtalo de nuevo en unos minutos.",
  internal_error: "Se produjo un error interno al cerrar el mes. Inténtalo de nuevo más tarde.",
  bracket_table_empty: "Una tabla de tramos necesita al menos un tramo.",
  bracket_table_must_start_at_zero: "El primer tramo de una tabla debe empezar en 0.",
  bracket_table_not_contiguous: "Cada tramo debe empezar exactamente donde acaba el anterior.",
  last_bracket_must_be_open: "El último tramo de una tabla no puede tener límite superior.",
  overlapping_schedules: "Más de una tarifa coincide con un flight en el mismo paso: revisa sus vigencias.",
  schedule_overlaps_existing: "Otra tarifa con la misma clave está vigente durante parte de esta vigencia.",
  reference_not_found: "El grupo, la agencia o el canal indicado no existe.",
  revenue_must_not_be_negative: "El ingreso y la posición del contador no pueden ser negativos.",
  duplicate_flight_id: "Un flight aparece más de una vez en la petición.",
  validity_ends_before_it_starts: "Una tarifa no puede acabar antes de empezar.",
  not_found: "La ruta solicitada no existe.",
  method_not_allowed: "La operación solicitada no está permitida.",
  http_error: "No se pudo atender la petición.",
};

function previousMonthOpen(message: string | undefined, target: ClosingTarget): string {
  const closing = monthOfYear(target.year, target.month);
  const match = message === undefined ? null : BLOCKING_MONTH.exec(message);
  const index = match === null ? -1 : MONTH_CODES.indexOf(match[2] ?? "");
  if (match === null || index < 0) return `Hay un mes anterior sin cerrar. Ciérralo antes de cerrar ${closing}.`;
  return `Hay un mes anterior sin cerrar: ${monthOfYear(match[1] ?? "", index + 1)}. Ciérralo antes de cerrar ${closing}.`;
}

/** The Spanish message for a failed closing, from the backend's code. `message` is only read for the blocking month. */
export function closingErrorMessage(code: string | undefined, message: string | undefined, target: ClosingTarget): string {
  if (code === "previous_month_open") return previousMonthOpen(message, target);
  if (code !== undefined && code in MESSAGE_BY_CODE) return MESSAGE_BY_CODE[code] ?? GENERIC_CLOSING_ERROR;
  return GENERIC_CLOSING_ERROR;
}

export function closedFlightsMessage(closed: number, target: ClosingTarget): string {
  const period = monthOfYear(target.year, target.month);
  if (closed === 0) return "No hay flights terminados en este mes";
  if (closed === 1) return `Se cerró 1 flight de ${period}`;
  return `Se cerraron ${closed} flights de ${period}`;
}

export function flightCount(count: number): string {
  return count === 1 ? "1 flight" : `${count} flights`;
}

export const ACCRUED_LABEL = "Devengado";

export const ACCRUED_HELP =
  "Ingreso proporcional a los días transcurridos del flight; en un flight cerrado es igual a la venta contratada.";

/** «10 de 14 días»: the days of a running flight counted so far and the days of the whole flight, as received. */
export function daysLegend(accruedDays: number, windowDays: number): string {
  return `${accruedDays} de ${windowDays} días`;
}

/** «Entregado X de Y impresiones»: what was delivered of what was contracted, as received. */
export function deliveryLegend(delivered: number, contracted: number): string {
  return `Entregado ${formatInteger(delivered)} de ${formatInteger(contracted)} impresiones`;
}
