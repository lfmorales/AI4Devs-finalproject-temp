"use client";

import { Modal } from "@/lib/components/Modal";
import { monthOfYear, type ClosingTarget } from "./messages";

interface CloseMonthDialogProps {
  target: ClosingTarget;
  submitting: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Explains what closing does and asks for a confirmation; nothing is sent before it. */
export function CloseMonthDialog({ target, submitting, onConfirm, onCancel }: CloseMonthDialogProps) {
  return (
    <Modal title={`Cerrar ${monthOfYear(target.year, target.month)}`} closable={!submitting} onClose={onCancel}>
      <p>
        Cerrar el mes congela las tasas de rebate y de plataforma de los flights terminados: sus cifras dejan de
        depender de las tarifas vigentes. Se cerrarán los flights terminados de todas las campañas del mes. Esta acción
        no se puede deshacer.
      </p>
      <div className="dialog-actions">
        <button type="button" className="btn-primary" disabled={submitting} onClick={onConfirm}>
          Confirmar cierre
        </button>
        <button type="button" disabled={submitting} onClick={onCancel}>Cancelar</button>
      </div>
    </Modal>
  );
}
