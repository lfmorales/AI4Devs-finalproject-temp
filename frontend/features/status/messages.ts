import { formatDecimal } from "@/lib/format/decimal";

/** What the backend names when a carry-over is above the shortfall: "... fell short by 100000". */
const SHORTFALL = /fell short by (\d+(?:\.\d+)?)/;

const MESSAGE_BY_CODE: Record<string, string> = {
  invalid_carryover: "El arrastre necesita un volumen entero de cero o más y un motivo.",
  no_previous_flight: "Es el primer flight de la línea: no tiene un flight anterior del que arrastrar.",
  previous_flight_not_ended: "El flight anterior de la línea aún no ha terminado: el arrastre se podrá registrar cuando acabe.",
  month_closed: "El mes de este flight ya está cerrado: su arrastre no se puede cambiar.",
  flight_not_found: "Este flight ya no existe. Recarga la página.",
  validation_error: "La petición no es válida: revisa el volumen y el motivo.",
};

export const GENERIC_CARRYOVER_ERROR = "No se pudo guardar el arrastre. Inténtalo de nuevo más tarde.";

/** The Spanish message of a refused carry-over, with what to do; `message` is only read for the shortfall. */
export function carryoverErrorMessage(code: string | undefined, message: string | undefined): string {
  if (code === "carryover_exceeds_shortfall") {
    const match = message === undefined ? null : SHORTFALL.exec(message);
    const most = match === null ? "" : `: como máximo ${formatDecimal(match[1] ?? "")}`;
    return `El arrastre supera lo que le faltó al flight anterior${most}. Indica un volumen menor.`;
  }
  if (code !== undefined && code in MESSAGE_BY_CODE) return MESSAGE_BY_CODE[code] ?? GENERIC_CARRYOVER_ERROR;
  return GENERIC_CARRYOVER_ERROR;
}
