const MOMENT = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/;

/** «02/11/2026 10:15» from the API's "2026-11-02T10:15:30.123456": the text is rearranged, never converted. */
export function formatMoment(value: string): string {
  const match = MOMENT.exec(value);
  if (match === null) return value;
  const [, year, month, day, hour, minute] = match;
  return `${day}/${month}/${year} ${hour}:${minute}`;
}
