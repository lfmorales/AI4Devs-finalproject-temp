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

/** Today's day of the month in Madrid, where the application's calendar lives. */
export function madridDayOfMonth(now: Date = new Date()): number {
  return Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Madrid", day: "numeric" }).format(now));
}

export const RUNNING_FLIGHT_SKIP_REASON =
  "Today (Madrid) is the first of the month: no flight has days elapsed yet, so there is nothing running to read.";
