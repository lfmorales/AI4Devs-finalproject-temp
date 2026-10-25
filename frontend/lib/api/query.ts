/** Builds "?a=1&b=2" from the parameters that have a value; nothing at all when none does. */
export function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const query = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    query.set(name, String(value));
  }
  const text = query.toString();
  return text === "" ? "" : `?${text}`;
}
