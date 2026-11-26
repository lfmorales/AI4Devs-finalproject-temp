"use client";

import { useId, useState } from "react";

import { browserApiClient } from "@/lib/api/browser-client";
import type { ApiError } from "@/lib/api/client";
import { putCarryover, type CampaignStatusRow } from "@/lib/api/status";
import { Modal } from "@/lib/components/Modal";
import { metricLabel } from "@/lib/format/delivery-metric";
import { NEW_CARRYOVER, toCarryoverRequest, type CarryoverFields } from "./carryover-form";
import { carryoverErrorMessage } from "./messages";

interface CarryoverDialogProps {
  row: CampaignStatusRow;
  onDone: () => void;
  onCancel: () => void;
  onBlocked: (kind: "unauthenticated" | "forbidden") => void;
}

/** The volume carried to the flight from the previous flight of its line, and why. No amount, no billable flag. */
export function CarryoverDialog({ row, onDone, onCancel, onBlocked }: CarryoverDialogProps) {
  const [fields, setFields] = useState<CarryoverFields>(NEW_CARRYOVER);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const volumeId = useId();
  const reasonId = useId();
  const request = toCarryoverRequest(fields);

  async function save() {
    if (request === null) return;
    setSubmitting(true);
    setError(null);
    try {
      await putCarryover(browserApiClient(), row.flight.id, request);
      onDone();
    } catch (caught) {
      const failure = caught as Partial<ApiError>;
      if (failure.kind === "unauthenticated" || failure.kind === "forbidden") onBlocked(failure.kind);
      else setError(carryoverErrorMessage(failure.code, failure.message));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal title={`Arrastre de ${row.campaign.name} · línea ${row.line_number}`} closable={!submitting} onClose={onCancel}>
      <p>
        Volumen que no entregó el flight anterior de la línea y pasa a este, en {metricLabel(row.delivery_metric)}. Un
        volumen de 0 quita el arrastre.
      </p>
      <div className="form-field">
        <label htmlFor={volumeId}>Volumen</label>
        <input
          id={volumeId}
          type="text"
          inputMode="numeric"
          value={fields.volume}
          onChange={(event) => setFields({ ...fields, volume: event.target.value })}
        />
      </div>
      <div className="form-field">
        <label htmlFor={reasonId}>Motivo</label>
        <textarea id={reasonId} value={fields.reason} onChange={(event) => setFields({ ...fields, reason: event.target.value })} />
      </div>
      {error !== null && <div role="alert" className="notice notice-error">{error}</div>}
      <div className="dialog-actions">
        <button type="button" className="btn-primary" disabled={request === null || submitting} onClick={() => void save()}>
          Guardar arrastre
        </button>
        <button type="button" disabled={submitting} onClick={onCancel}>Cancelar</button>
      </div>
    </Modal>
  );
}
