import { formatQuantity } from "@/lib/format/decimal";
import { metricLabel, type DeliveryMetric } from "@/lib/format/delivery-metric";
import { formatInteger } from "@/lib/format/integer";
import type { BillingBasis } from "@/lib/api/margin";
import type { VolumeCommitment } from "@/lib/api/volume-commitment";
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

/** What the backend names when a DSP has not loaded the month's last day: "... of 2026-11 from Equativ is not ...". */
const NOT_LOADED_DSP = /\d{4}-\d{2} from (.+?) is not loaded/;

function monthDeliveryNotLoaded(message: string | undefined, target: ClosingTarget): string {
  const closing = monthOfYear(target.year, target.month);
  const match = message === undefined ? null : NOT_LOADED_DSP.exec(message);
  const missing = match === null ? "falta cargar la entrega" : `${match[1] ?? ""} aún no ha cargado la entrega`;
  return `No se puede cerrar ${closing}: ${missing} de su último día. Espera a la ingesta de ese día y vuelve a cerrar el mes.`;
}

/** What the backend names when campaigns block the closing: "...: A (pending review); B (in progress). Review ...". */
const NOT_REVIEWED_LIST = /has campaigns not reviewed: (.+)\. Review them/;
const NOT_REVIEWED_ITEM = /^(.*) \((pending review|in progress)\)$/;
const REVIEW_STATE_IN_SPANISH: Record<string, string> = { "pending review": "pendiente de revisión", "in progress": "en curso" };
const REVIEW_THEN_CLOSE =
  "Márcalas como revisadas en Facturación cuando hayan terminado sus flights y vuelve a cerrar el mes.";

function monthNotReviewed(message: string | undefined, target: ClosingTarget): string {
  const closing = monthOfYear(target.year, target.month);
  const listed = message === undefined ? null : NOT_REVIEWED_LIST.exec(message);
  const items = (listed?.[1] ?? "").split("; ").map((item) => NOT_REVIEWED_ITEM.exec(item));
  if (listed === null || items.some((item) => item === null)) {
    return `No se puede cerrar ${closing}: hay campañas sin revisar. ${REVIEW_THEN_CLOSE}`;
  }
  const named = items.map((item) => `${item?.[1] ?? ""} (${REVIEW_STATE_IN_SPANISH[item?.[2] ?? ""] ?? ""})`).join(", ");
  return `No se puede cerrar ${closing}: hay campañas sin revisar: ${named}. ${REVIEW_THEN_CLOSE}`;
}

/** The Spanish message for a failed closing, from the backend's code. `message` is only read for a month, a DSP or
 * the campaigns that block it. */
export function closingErrorMessage(code: string | undefined, message: string | undefined, target: ClosingTarget): string {
  if (code === "previous_month_open") return previousMonthOpen(message, target);
  if (code === "month_delivery_not_loaded") return monthDeliveryNotLoaded(message, target);
  if (code === "month_not_reviewed") return monthNotReviewed(message, target);
  if (code !== undefined && code in MESSAGE_BY_CODE) return MESSAGE_BY_CODE[code] ?? GENERIC_CLOSING_ERROR;
  return GENERIC_CLOSING_ERROR;
}

export function closedFlightsMessage(closed: number, target: ClosingTarget): string {
  const period = monthOfYear(target.year, target.month);
  if (closed === 0) return "No hay flights terminados en este mes";
  if (closed === 1) return `Se cerró 1 flight de ${period}`;
  return `Se cerraron ${closed} flights de ${period}`;
}

/** Null for a month closed once or not at all; a warning when a flight registered late was closed by a later closing. */
export function closingsMessage(closings: number, target: ClosingTarget): string | null {
  if (closings <= 1) return null;
  return `${monthOfYear(target.year, target.month)} tiene ${closings} cierres: se cerró un flight dado de alta después `
    + "de un cierre anterior. Las cifras de los cierres anteriores no cambian.";
}

export function flightCount(count: number): string {
  return count === 1 ? "1 flight" : `${count} flights`;
}

/** The revenue of a level is its billing: «Facturable», or «Facturable a la fecha» while a flight of it runs. */
export const BILLING_LABEL = "Facturable";
export const BILLING_TO_DATE_LABEL = "Facturable a la fecha";

export function billingLabel(includesRunning: boolean): string {
  return includesRunning ? BILLING_TO_DATE_LABEL : BILLING_LABEL;
}

export const BILLING_HELP =
  "Lo que se factura del flight: el menor entre lo entregado y lo contratado (más el arrastre si es facturable), "
  + "o lo que fije un ajuste; en un flight en curso, lo facturable hasta ayer. En una línea objetivo, lo que comunica el DSP.";

/** A flight whose billing an adjustment sets, not the rule of the lesser. */
export const ADJUSTED_LABEL = "Ajustado";
const ADJUSTED_BASES: readonly (BillingBasis | null)[] = ["delivered", "contracted", "custom"];
const ADJUSTED_HELP_BY_BASIS: Record<string, string> = {
  delivered: "Ajuste en vigor: se factura todo lo entregado, sin tope.",
  contracted: "Ajuste en vigor: se factura el tope, lo contratado más el arrastre facturable.",
  custom: "Ajuste en vigor: se factura un importe fijo.",
};

export function isAdjusted(basis: BillingBasis | null): boolean {
  return ADJUSTED_BASES.includes(basis);
}

export function adjustedHelp(basis: BillingBasis | null): string {
  return ADJUSTED_HELP_BY_BASIS[basis ?? ""] ?? "";
}

/** Why the closing control is off while the billing read reports a campaign in progress or pending review. */
export const PENDING_REVIEW_REASON = "Hay campañas pendientes de revisión";

/** «10 de 14 días»: the days of a running flight counted so far and the days of the whole flight, as received. */
export function daysLegend(accruedDays: number, windowDays: number): string {
  return `${accruedDays} de ${windowDays} días`;
}

/** «Entregado X de Y OTS» or «… impresiones»: what was delivered of what was contracted, in the unit named, as received. */
export function deliveryLegend(delivered: string, contracted: number, metric: DeliveryMetric): string {
  return `Entregado ${formatQuantity(delivered)} de ${formatInteger(contracted)} ${metricLabel(metric)}`;
}

/** The sale of a level: what was contracted, or for a target line what its target is worth. */
export const CONTRACTED_SALE_LABEL = "Venta contratada";
export const TARGET_SALE_LABEL = "Venta objetivo";

export function saleLabel(commitment: VolumeCommitment | null): string {
  return commitment === "target" ? TARGET_SALE_LABEL : CONTRACTED_SALE_LABEL;
}

/** The served impressions of a target flight at the line's CPM, as the server computed it. */
export const GROSS_LABEL = "Bruto";

export const GROSS_DIFFERS_LABEL = "Bruto distinto del gasto";
export const GROSS_DIFFERS_HELP =
  "El bruto (impresiones servidas por el CPM de la línea) se aleja más de un 1 % del gasto del comprador que comunica "
  + "el DSP. Revisa el CPM de la línea y el paquete vinculado.";

export const DATA_COST_LABEL = "Coste de datos";
export const DATA_COST_HELP =
  "El DSP comunica costes de datos de terceros o de audiencia en este flight. No se restan del margen: revisa con el "
  + "comprador si deben repercutirse.";

export const DELIVERY_CHANGED_LABEL = "Cambió tras el cierre";
export const DELIVERY_CHANGED_HELP =
  "La entrega guardada de este flight cambió después del cierre del mes: el DSP reexpresó sus cifras o se desvinculó "
  + "la línea. El margen cerrado no cambia. El margen informativo usa la extraprima y las tarifas del cierre con la "
  + "entrega de hoy. Revisa con el DSP si la nueva entrega es correcta. Si lo es, la diferencia se regulariza fuera de "
  + "la aplicación: el mes cerrado no se reabre.";
export const DELIVERY_CHANGE_NOTE =
  "Margen informativo con la extraprima y las tarifas del cierre: solo cambia la entrega y no suma en ningún total.";
