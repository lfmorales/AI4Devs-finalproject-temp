"use client";

import { useId, useState } from "react";

interface ResolveDialogProps {
  exceptionId: number;
  submitting: boolean;
  onConfirm: (note: string | null) => void;
  onCancel: () => void;
}

/** Asks for the optional note and a confirmation; nothing is sent before the confirmation. */
export function ResolveDialog({ exceptionId, submitting, onConfirm, onCancel }: ResolveDialogProps) {
  const [note, setNote] = useState("");
  const noteId = useId();

  return (
    <div role="dialog" aria-label={`Resolver excepción ${exceptionId}`} style={{ border: "1px solid #d1d5db", padding: "1rem", margin: "1rem 0" }}>
      <p>Marcar la excepción {exceptionId} como resuelta. No se reprocesa ninguna entrega.</p>
      <label htmlFor={noteId} style={{ display: "block", fontWeight: "600" }}>Nota (opcional)</label>
      <textarea id={noteId} value={note} onChange={(event) => setNote(event.target.value)} rows={3} style={{ width: "100%" }} />
      <div style={{ display: "flex", gap: "1rem", marginTop: "0.5rem" }}>
        <button type="button" disabled={submitting} onClick={() => onConfirm(note.trim() === "" ? null : note.trim())}>
          Confirmar resolución
        </button>
        <button type="button" disabled={submitting} onClick={onCancel}>Cancelar</button>
      </div>
    </div>
  );
}
