// es-ES leaves four-digit numbers ungrouped by default; 'always' groups them too (1.234).
const integer = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0, useGrouping: "always" });

export function formatInteger(value: number): string {
  return integer.format(value);
}
