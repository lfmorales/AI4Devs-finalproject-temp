"use client";

import { useId, useState } from "react";

import { Modal } from "@/lib/components/Modal";

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
    <Modal title={`Resolver excepción ${exceptionId}`} closable={!submitting} onClose={onCancel}>
      <p>Marcar la excepción {exceptionId} como resuelta. No se reprocesa ninguna entrega.</p>
      <label htmlFor={noteId} style={{ display: "block", fontWeight: "600" }}>Nota (opcional)</label>
      <textarea id={noteId} value={note} onChange={(event) => setNote(event.target.value)} rows={3} style={{ width: "100%" }} />
      <div style={{ display: "flex", gap: "1rem", marginTop: "0.5rem" }}>
        <button type="button" className="btn-primary" disabled={submitting} onClick={() => onConfirm(note.trim() === "" ? null : note.trim())}>
          Confirmar resolución
        </button>
        <button type="button" disabled={submitting} onClick={onCancel}>Cancelar</button>
      </div>
    </Modal>
  );
}
