"use client";

import { adjustmentHistory, type HistoryItem } from "@/lib/api/billing";
import { useApiCall } from "@/lib/api/useApiCall";
import { Modal } from "@/lib/components/Modal";
import { formatMoney } from "@/lib/format/decimal";
import { formatMoment } from "@/lib/format/moment";
import { BASIS_LABEL, NO_ADJUSTMENTS } from "./messages";

function historyLine(item: HistoryItem): string {
  const amount = item.amount === null ? "" : ` ${formatMoney(item.amount)}`;
  const inForce = item.in_force ? " · En vigor" : "";
  return `${BASIS_LABEL[item.basis]}${amount} · ${item.reason} · usuario ${item.created_by} · ${formatMoment(item.created_at)}${inForce}`;
}

/** Every adjustment of a flight, latest first, as the server lists them. */
export function HistoryDialog({ flightId, onClose }: { flightId: number; onClose: () => void }) {
  const { state } = useApiCall(`adjustments-${flightId}`, (client) => adjustmentHistory(client, flightId));
  return (
    <Modal title="Historial de ajustes" closable onClose={onClose}>
      {state.status === "loading" && <p role="status">Cargando historial…</p>}
      {(state.status === "error" || state.status === "forbidden" || state.status === "unauthenticated") && (
        <p role="alert" className="notice notice-error">No se pudo cargar el historial. Inténtalo de nuevo más tarde.</p>
      )}
      {state.status === "ready" && state.data.length === 0 && <p>{NO_ADJUSTMENTS}</p>}
      {state.status === "ready" && state.data.length > 0 && (
        <ul>{state.data.map((item) => <li key={item.id}>{historyLine(item)}</li>)}</ul>
      )}
      <div className="dialog-actions">
        <button type="button" onClick={onClose}>Cerrar</button>
      </div>
    </Modal>
  );
}
