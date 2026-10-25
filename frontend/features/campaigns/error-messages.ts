import { FLIGHT_MESSAGES } from "./schema";

/** The backend codes about a line's dates and flights, in Spanish. Never the backend's own text. */
const MESSAGE_BY_CODE: Record<string, string> = {
  line_dates_outside_campaign: FLIGHT_MESSAGES.datesOutside,
  line_dates_invalid: FLIGHT_MESSAGES.lineEndBeforeStart,
  flight_volumes_incomplete: FLIGHT_MESSAGES.incomplete,
  flight_volumes_mismatch: FLIGHT_MESSAGES.mismatch,
  flight_volume_not_positive: FLIGHT_MESSAGES.notPositive,
  volume_too_small_for_flights: FLIGHT_MESSAGES.volumeTooSmall,
};

export const SEVERAL_LINES_PREFIX = "En alguna de estas líneas: ";

/** The Spanish message of a known code, or null for any other. */
export function lineErrorMessage(code: string | undefined): string | null {
  return code !== undefined && code in MESSAGE_BY_CODE ? (MESSAGE_BY_CODE[code] ?? null) : null;
}

/** What the mapping needs to know about a line. */
export interface LineKind {
  id: string;
  /** The line sets its own dates (does not inherit the campaign's). */
  hasOwnDates: boolean;
  /** The line has a manual split that is still current. */
  isManual: boolean;
}

/**
 * The lines that can have caused a registration error. The registration answers only a code, with no line
 * number, so the lines are narrowed by what each code is about: own dates, a manual split, or a proportional one.
 */
export function candidateLineIds(code: string, lines: LineKind[]): string[] {
  if (code.startsWith("line_dates_")) return lines.filter((l) => l.hasOwnDates).map((l) => l.id);
  if (code.startsWith("flight_volume")) return lines.filter((l) => l.isManual).map((l) => l.id);
  if (code === "volume_too_small_for_flights") return lines.filter((l) => !l.isManual).map((l) => l.id);
  return [];
}

export interface RegistrationLineErrors {
  /** Message per line id for the candidate lines; empty when no line can be the cause. */
  byLine: Record<string, string>;
  /** Set when there is no candidate: the error belongs to the form. */
  formLevel: string | null;
}

/** Where a registration 422 with a known code is shown. Null when the code is not one of these. */
export function registrationLineErrors(code: string | undefined, lines: LineKind[]): RegistrationLineErrors | null {
  const message = lineErrorMessage(code);
  if (!code || message === null) return null;
  const candidates = candidateLineIds(code, lines);
  if (candidates.length === 0) return { byLine: {}, formLevel: message };
  const text = candidates.length === 1 ? message : `${SEVERAL_LINES_PREFIX}${message}`;
  return { byLine: Object.fromEntries(candidates.map((id) => [id, text])), formLevel: null };
}
