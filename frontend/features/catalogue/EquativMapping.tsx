"use client";

import { useEffect, useId, useState } from "react";

import type { FatalKind } from "@/features/linking/LinePickerDialog";
import { HISTORY_LOAD_WARNING } from "@/features/linking/messages";
import { createApiClient, type ApiError } from "@/lib/api/client";
import {
  createDspMapping,
  listDspCatalog,
  listUnmappedLines,
  type DspCatalogItem,
  type UnmappedLine,
} from "@/lib/api/dsp-catalog";
import { useApiCall } from "@/lib/api/useApiCall";
import { Modal } from "@/lib/components/Modal";
import {
  INVALID_EQUATIV_PACKAGE,
  MAPPING_ERROR_MESSAGES,
  MAPPING_FAILED_MESSAGE,
  NO_RECENT_PACKAGE_DELIVERY,
  packageLinkedMessage,
  VALIDATION_MESSAGES,
} from "./messages";

const EQUATIV = "Equativ";
const DIALOG_LABEL = "Vincular una línea de Equativ";
const SUGGESTION_LIMIT = 50;

function lineName(line: UnmappedLine): string {
  return `${line.campaign_name}, línea ${line.line_number}`;
}

function describeLine(line: UnmappedLine): string {
  return `${lineName(line)}, del ${line.start_date} al ${line.end_date}`;
}

/** A package matches what is written when its id or its name contains it; nothing written matches every package. */
function matches(item: DspCatalogItem, written: string): boolean {
  const needle = written.trim().toLowerCase();
  if (needle === "") return true;
  return [item.external_campaign_id, item.campaign_name].some((part) => part.toLowerCase().includes(needle));
}

interface Outcome {
  messages: string[];
  needsHistoryLoad: boolean;
}

/** The unmapped Equativ packages of the catalogue, offered while the package of `line` is written. */
function PackageSuggestions({ line, written, onPick }: { line: UnmappedLine; written: string; onPick: (id: string) => void }) {
  const { state } = useApiCall(`equativ-packages-${line.dsp_id}`, (client) =>
    listDspCatalog(client, { dspId: line.dsp_id, mapped: false, limit: SUGGESTION_LIMIT }),
  );
  if (state.status !== "ready") return null;
  const shown = state.data.items.filter((item) => matches(item, written));
  if (shown.length === 0) return null;
  return (
    <ul aria-label="Paquetes del catálogo de Equativ" className="suggestions">
      {shown.map((item) => (
        <li key={item.external_campaign_id}>
          <button type="button" onClick={() => onPick(item.external_campaign_id)}>
            {item.external_campaign_id} · {item.campaign_name}
          </button>
        </li>
      ))}
    </ul>
  );
}

function EquativMappingDialog({ onMapped, onCancel, onFatal }: {
  onMapped: (outcome: Outcome) => void;
  onCancel: () => void;
  onFatal: (kind: FatalKind) => void;
}) {
  const { state } = useApiCall("unmapped-lines-equativ", (client) => listUnmappedLines(client));
  const [chosenId, setChosenId] = useState<number | null>(null);
  const [written, setWritten] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [fieldProblem, setFieldProblem] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const fieldId = useId();
  const fieldProblemId = useId();
  const loadFailure = state.status === "unauthenticated" || state.status === "forbidden" ? state.status : null;

  useEffect(() => {
    if (loadFailure) onFatal(loadFailure);
  }, [loadFailure, onFatal]);

  const lines = state.status === "ready" ? state.data.filter((line) => line.dsp_name === EQUATIV) : [];
  const chosen = lines.find((line) => line.id === chosenId) ?? null;
  const packageId = written.trim();

  async function link(line: UnmappedLine) {
    setSubmitting(true);
    setFieldProblem(null);
    setProblem(null);
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL;
      if (!baseUrl) throw new Error("API URL not configured");
      // One package identifies an Equativ line: it is sent as both identifiers of the pair.
      const result = await createDspMapping(createApiClient({ baseUrl }), line.id, {
        external_campaign_id: packageId,
        external_line_item_id: packageId,
      });
      const messages = [packageLinkedMessage(packageId, lineName(line)), VALIDATION_MESSAGES[result.validation]];
      if (result.last_impressions_date === null) messages.push(NO_RECENT_PACKAGE_DELIVERY);
      onMapped({ messages, needsHistoryLoad: result.needs_history_load });
    } catch (caught) {
      const error = caught as Partial<ApiError>;
      if (error.kind === "unauthenticated" || error.kind === "forbidden") {
        onFatal(error.kind);
        return;
      }
      const spanish = (error.code && MAPPING_ERROR_MESSAGES[error.code]) || MAPPING_FAILED_MESSAGE;
      if (error.code === INVALID_EQUATIV_PACKAGE) setFieldProblem(spanish);
      else setProblem(spanish);
    } finally {
      setSubmitting(false);
    }
  }

  function body() {
    if (state.status === "loading") return <div role="status" className="notice notice-info">Cargando líneas…</div>;
    if (state.status === "error") return <p>No se pudieron cargar las líneas. Inténtalo de nuevo más tarde.</p>;
    if (state.status !== "ready") return null;
    if (lines.length === 0) return <p>No hay líneas de Equativ sin vincular</p>;
    return (
      <>
        <div role="radiogroup" aria-label="Líneas de Equativ sin vincular">
          {lines.map((line) => (
            <label key={line.id}>
              <input type="radio" name="equativ-line" checked={line.id === chosenId} onChange={() => setChosenId(line.id)} />{" "}
              {describeLine(line)}
            </label>
          ))}
        </div>
        {chosen && (
          <div>
            <label htmlFor={fieldId}>Paquete de Equativ (auctionPackageDealId)</label>
            <input
              id={fieldId}
              type="text"
              inputMode="numeric"
              autoComplete="off"
              value={written}
              aria-invalid={fieldProblem !== null}
              aria-describedby={fieldProblem === null ? undefined : fieldProblemId}
              onChange={(event) => { setWritten(event.target.value); setFieldProblem(null); }}
            />
            {fieldProblem && <p id={fieldProblemId} role="alert" className="field-error">{fieldProblem}</p>}
            <PackageSuggestions line={chosen} written={written} onPick={(id) => { setWritten(id); setFieldProblem(null); }} />
          </div>
        )}
      </>
    );
  }

  return (
    <Modal title={DIALOG_LABEL} closable={!submitting} onClose={onCancel}>
      {body()}
      {problem && <div role="alert" className="notice notice-error">{problem}</div>}
      <div className="dialog-actions">
        <button
          type="button"
          className="btn-primary"
          disabled={submitting || chosen === null || packageId === ""}
          onClick={() => chosen && void link(chosen)}
        >
          Vincular paquete
        </button>
        <button type="button" disabled={submitting} onClick={onCancel}>Cancelar</button>
      </div>
    </Modal>
  );
}

/** Mapping a line on Equativ by writing its auction package, suggested from the catalogue but never required from it. */
export function EquativMapping({ onFatal }: { onFatal: (kind: FatalKind) => void }) {
  const [open, setOpen] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  return (
    <section aria-label="Líneas de Equativ">
      <button type="button" onClick={() => { setOutcome(null); setOpen(true); }}>{DIALOG_LABEL}</button>
      {outcome && (
        <div role="status" className="notice notice-success">
          {outcome.messages.map((message) => <p key={message}>{message}</p>)}
        </div>
      )}
      {outcome?.needsHistoryLoad && <div role="alert" className="notice notice-warning">{HISTORY_LOAD_WARNING}</div>}
      {open && (
        <EquativMappingDialog
          onMapped={(result) => { setOutcome(result); setOpen(false); }}
          onCancel={() => setOpen(false)}
          onFatal={onFatal}
        />
      )}
    </section>
  );
}
