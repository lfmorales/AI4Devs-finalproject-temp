const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;

/**
 * Formats a decimal string in es-ES the way the application does: dots between thousands, a comma before the
 * decimals, the integer and decimal parts handled apart and never converted to a number.
 */
export function formatDecimalEsEs(value: string): string {
  const match = DECIMAL.exec(value);
  if (match === null) throw new Error(`Not a decimal string: ${value}`);
  const [, sign = "", integer = "", fraction] = match;
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${sign}${grouped}${fraction === undefined ? "" : `,${fraction}`}`;
}

/**
 * A delivered volume as the application shows it: es-ES, the decimals received minus the trailing zeros that only pad
 * them ("280000.5000" reads 280.000,5; "198500.0000", 198.500).
 */
export function formatQuantityEsEs(value: string): string {
  return formatDecimalEsEs(value.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, ""));
}

/** The unit as the application names it: «OTS» or «impresiones». */
export function unitLabel(metric: "impressions" | "ots"): string {
  return metric === "ots" ? "OTS" : "impresiones";
}

/** Today's day of the month in Madrid, where the application's calendar lives. */
export function madridDayOfMonth(now: Date = new Date()): number {
  return Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Madrid", day: "numeric" }).format(now));
}

export const RUNNING_FLIGHT_SKIP_REASON =
  "Today (Madrid) is the first of the month: no flight has days elapsed yet, so there is nothing running to read.";
