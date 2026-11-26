import type { CarryoverRequest } from "@/lib/api/status";

/** What the carry-over form holds, as text. */
export interface CarryoverFields {
  volume: string;
  reason: string;
}

export const NEW_CARRYOVER: CarryoverFields = { volume: "", reason: "" };

const WHOLE_VOLUME = /^\d+$/;

/** The request the form sends, or null while it is incomplete: a whole volume, zero or more, and a reason. The volume
 * is the only number the screen parses, to send it as the API's integer; nothing is computed with it. */
export function toCarryoverRequest(fields: CarryoverFields): CarryoverRequest | null {
  const volume = fields.volume.trim();
  const reason = fields.reason.trim();
  if (!WHOLE_VOLUME.test(volume) || reason === "") return null;
  return { volume: Number(volume), reason };
}
