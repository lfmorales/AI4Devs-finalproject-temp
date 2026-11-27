"use client";

import { useId, useState } from "react";

import { adjustFlight, type AdjustmentBasis, type BillingMonth } from "@/lib/api/billing";
import { browserApiClient } from "@/lib/api/browser-client";
import type { ApiError } from "@/lib/api/client";
import { Modal } from "@/lib/components/Modal";
import { NEW_ADJUSTMENT, toAdjustmentRequest, type AdjustmentFields } from "./adjustment-form";
import { adjustmentErrorMessage, BASIS_LABEL, BASIS_ORDER } from "./messages";

interface AdjustmentDialogProps {
  flightId: number;
  month: BillingMonth;
  onDone: () => void;
  onCancel: () => void;
  /** A 401 or a 403: the page shows its own screen for them. */
  onBlocked: (kind: "unauthenticated" | "forbidden") => void;
}

/** The basis, the amount only for a custom billing, and the mandatory reason. The server computes the billing. */
export function AdjustmentDialog({ flightId, month, onDone, onCancel, onBlocked }: AdjustmentDialogProps) {
  const [fields, setFields] = useState<AdjustmentFields>(NEW_ADJUSTMENT);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const basisId = useId();
  const amountId = useId();
  const reasonId = useId();
  const request = toAdjustmentRequest(fields);

  async function save() {
    if (request === null) return;
    setSubmitting(true);
    setError(null);
    try {
      await adjustFlight(browserApiClient(), flightId, request);
      onDone();
    } catch (caught) {
      const failure = caught as Partial<ApiError>;
      if (failure.kind === "unauthenticated" || failure.kind === "forbidden") onBlocked(failure.kind);
      else setError(adjustmentErrorMessage(failure.code, failure.message, { month }));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal title="Ajustar la facturación" closable={!submitting} onClose={onCancel}>
      <div className="form-field">
        <label htmlFor={basisId}>Base</label>
        <select
          id={basisId}
          value={fields.basis}
          onChange={(event) => setFields({ ...fields, basis: event.target.value as AdjustmentBasis })}
        >
          {BASIS_ORDER.map((basis) => <option key={basis} value={basis}>{BASIS_LABEL[basis]}</option>)}
        </select>
      </div>
      {fields.basis === "custom" && (
        <div className="form-field">
          <label htmlFor={amountId}>Importe</label>
          <input
            id={amountId}
            type="text"
            inputMode="decimal"
            value={fields.amount}
            onChange={(event) => setFields({ ...fields, amount: event.target.value })}
          />
        </div>
      )}
      <div className="form-field">
        <label htmlFor={reasonId}>Motivo</label>
        <textarea id={reasonId} value={fields.reason} onChange={(event) => setFields({ ...fields, reason: event.target.value })} />
      </div>
      {error !== null && <div role="alert" className="notice notice-error">{error}</div>}
      <div className="dialog-actions">
        <button type="button" className="btn-primary" disabled={request === null || submitting} onClick={() => void save()}>
          Guardar ajuste
        </button>
        <button type="button" disabled={submitting} onClick={onCancel}>Cancelar</button>
      </div>
    </Modal>
  );
}
