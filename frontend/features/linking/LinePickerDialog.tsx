"use client";

import { useEffect, useId, useState } from "react";

import { listUnmappedLines, type UnmappedLine } from "@/lib/api/dsp-catalog";
import { useApiCall } from "@/lib/api/useApiCall";
import { Modal } from "@/lib/components/Modal";

export type FatalKind = "unauthenticated" | "forbidden";

interface LinePickerDialogProps {
  /** The dialog's accessible name. */
  label: string;
  submitting: boolean;
  /** A Spanish message about the last attempt, shown inside the dialog. */
  problem: string | null;
  onConfirm: (line: UnmappedLine) => void;
  onCancel: () => void;
  onFatal: (kind: FatalKind) => void;
}

function describeLine(line: UnmappedLine): string {
  return `${line.campaign_name}, línea ${line.line_number}, del ${line.start_date} al ${line.end_date}, ${line.dsp_name}`;
}

function matches(line: UnmappedLine, text: string): boolean {
  const needle = text.trim().toLowerCase();
  if (needle === "") return true;
  return [line.campaign_name, String(line.line_number), line.dsp_name].some((part) => part.toLowerCase().includes(needle));
}

/** Lists the lines with no mapping, with a text search, and hands the chosen one to `onConfirm`. */
export function LinePickerDialog({ label, submitting, problem, onConfirm, onCancel, onFatal }: LinePickerDialogProps) {
  const { state } = useApiCall("unmapped-lines", (client) => listUnmappedLines(client));
  const [search, setSearch] = useState("");
  const [chosenId, setChosenId] = useState<number | null>(null);
  const searchId = useId();
  const loadFailure = state.status === "unauthenticated" || state.status === "forbidden" ? state.status : null;

  useEffect(() => {
    if (loadFailure) onFatal(loadFailure);
  }, [loadFailure, onFatal]);

  const lines = state.status === "ready" ? state.data : [];
  const shown = lines.filter((line) => matches(line, search));
  const chosen = lines.find((line) => line.id === chosenId) ?? null;

  function body() {
    if (state.status === "loading") return <div role="status">Cargando líneas…</div>;
    if (state.status === "error") return <p>No se pudieron cargar las líneas. Inténtalo de nuevo más tarde.</p>;
    if (state.status !== "ready") return null;
    if (lines.length === 0) return <p>No hay líneas sin mapeo</p>;
    return (
      <>
        <label htmlFor={searchId} style={{ display: "block", fontWeight: "600" }}>Buscar línea</label>
        <input id={searchId} type="search" value={search} onChange={(event) => setSearch(event.target.value)} />
        {shown.length === 0 ? (
          <p>Ninguna línea coincide con la búsqueda</p>
        ) : (
          <div role="radiogroup" aria-label="Líneas sin mapeo" style={{ display: "grid", gap: "0.25rem", margin: "0.5rem 0", maxHeight: "16rem", overflowY: "auto" }}>
            {shown.map((line) => (
              <label key={line.id}>
                <input
                  type="radio"
                  name="unmapped-line"
                  checked={line.id === chosenId}
                  onChange={() => setChosenId(line.id)}
                />{" "}
                {describeLine(line)}
              </label>
            ))}
          </div>
        )}
      </>
    );
  }

  return (
    <Modal title={label} closable={!submitting} onClose={onCancel}>
      {body()}
      {problem && <div role="alert" style={{ backgroundColor: "#fee2e2", padding: "0.75rem", margin: "0.5rem 0" }}>{problem}</div>}
      <div style={{ display: "flex", gap: "1rem", marginTop: "0.5rem" }}>
        <button type="button" disabled={submitting || chosen === null} onClick={() => chosen && onConfirm(chosen)}>
          Confirmar vinculación
        </button>
        <button type="button" disabled={submitting} onClick={onCancel}>Cancelar</button>
      </div>
    </Modal>
  );
}
