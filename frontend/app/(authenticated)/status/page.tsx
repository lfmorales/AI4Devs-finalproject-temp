"use client";

import { useState } from "react";

import { CarryoverDialog } from "@/features/status/CarryoverDialog";
import { StatusTable } from "@/features/status/StatusTable";
import { getCampaignStatus, type CampaignStatusRow } from "@/lib/api/status";
import { useApiCall } from "@/lib/api/useApiCall";
import { useReportForbidden } from "@/lib/auth/ForbiddenPages";
import { useHasAnyRole } from "@/lib/auth/RolesContext";
import { AccessDeniedPage } from "@/lib/components/AccessDeniedPage";
import { SessionExpiredPage } from "@/lib/components/SessionExpiredPage";

export default function StatusPage() {
  const [reloads, setReloads] = useState(0);
  const [carrying, setCarrying] = useState<CampaignStatusRow | null>(null);
  const [saved, setSaved] = useState(false);
  const [blocked, setBlocked] = useState<"forbidden" | "unauthenticated" | null>(null);
  // The carry-over is written by operations and trading; finance and business only read it.
  const canCarry = useHasAnyRole("operations", "trading");
  const { state } = useApiCall(`campaign-status#${reloads}`, getCampaignStatus);
  useReportForbidden("/status", state.status === "forbidden");

  if (state.status === "unauthenticated" || blocked === "unauthenticated") return <SessionExpiredPage />;
  if (state.status === "forbidden") {
    return <AccessDeniedPage message="No tienes permiso para ver el estado de las campañas." />;
  }
  if (blocked === "forbidden") return <AccessDeniedPage message="No tienes permiso para registrar arrastres." />;

  return (
    <div>
      <h1>Estado de las campañas</h1>
      {saved && <div role="status" className="notice notice-success">Arrastre guardado</div>}
      {state.status === "loading" && <div role="status" className="notice notice-info">Cargando estado…</div>}
      {state.status === "error" && (
        <div role="alert" className="notice notice-error">
          No se pudo cargar el estado de las campañas. Inténtalo de nuevo más tarde.
        </div>
      )}
      {state.status === "ready" && state.data.length === 0 && (
        <div className="empty-state">
          <p>No hay campañas en curso</p>
        </div>
      )}
      {state.status === "ready" && state.data.length > 0 && (
        <StatusTable rows={state.data} onCarry={canCarry ? (row) => { setSaved(false); setCarrying(row); } : undefined} />
      )}
      {carrying !== null && (
        <CarryoverDialog
          row={carrying}
          onDone={() => {
            setCarrying(null);
            setSaved(true);
            setReloads((count) => count + 1);
          }}
          onCancel={() => setCarrying(null)}
          onBlocked={(kind) => {
            setCarrying(null);
            setBlocked(kind);
          }}
        />
      )}
    </div>
  );
}
