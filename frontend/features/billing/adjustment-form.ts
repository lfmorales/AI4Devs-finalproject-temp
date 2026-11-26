import type { AdjustmentBasis, AdjustmentRequest } from "@/lib/api/billing";

/** What the adjustment form holds, as text. */
export interface AdjustmentFields {
  basis: AdjustmentBasis;
  amount: string;
  reason: string;
}

export const NEW_ADJUSTMENT: AdjustmentFields = { basis: "minimum", amount: "", reason: "" };

/** Zero or more, with a comma or a point and at most two decimals: «4200», «4200,5», «4200.50». */
const AMOUNT = /^\d+(?:[.,]\d{1,2})?$/;

/** The request the form sends, or null while it is incomplete: a reason always, an amount only with `custom`. The
 * amount stays text: its comma becomes the point the API reads, and nothing else is done to it. */
export function toAdjustmentRequest(fields: AdjustmentFields): AdjustmentRequest | null {
  const reason = fields.reason.trim();
  if (reason === "") return null;
  if (fields.basis !== "custom") return { basis: fields.basis, amount: null, reason };
  const amount = fields.amount.trim();
  if (!AMOUNT.test(amount)) return null;
  return { basis: "custom", amount: amount.replace(",", "."), reason };
}
