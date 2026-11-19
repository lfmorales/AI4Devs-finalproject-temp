/** What a missing value looks like on screen. */
export const NO_VALUE = "—";

const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;
const NO_BREAK_SPACE = " ";

/**
 * Formats a decimal string in es-ES: a dot between thousands, a comma before the decimals. It works on the text
 * of the number and never converts it, so a value beyond what a floating-point number holds exactly is shown
 * whole, and the digits are exactly the ones received (no rounding, no trimming). Anything that is not a decimal
 * string comes back unchanged.
 */
export function formatDecimal(value: string): string {
  const match = DECIMAL.exec(value);
  if (match === null) return value;
  const [, sign = "", integer = "", fraction] = match;
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${sign}${grouped}${fraction === undefined ? "" : `,${fraction}`}`;
}

/**
 * A delivered volume (a four-decimal string of the API) in es-ES. Still text only, never a number: the decimals are
 * the ones received, minus the trailing zeros that only pad them ("280000.5000" reads 280.000,5; "198500.0000", 198.500).
 */
export function formatQuantity(value: string): string {
  return formatDecimal(value.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, ""));
}

export function formatMoney(value: string): string {
  return `${formatDecimal(value)}${NO_BREAK_SPACE}€`;
}

/** A percentage the server already computed; null (no revenue to divide by) is a dash. */
export function formatPercent(value: string | null): string {
  return value === null ? NO_VALUE : `${formatDecimal(value)}${NO_BREAK_SPACE}%`;
}
