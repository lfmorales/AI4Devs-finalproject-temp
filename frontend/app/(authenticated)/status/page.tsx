"use client";

import { StatusTable } from "@/features/status/StatusTable";
import { getCampaignStatus } from "@/lib/api/status";
import { useApiCall } from "@/lib/api/useApiCall";
import { useReportForbidden } from "@/lib/auth/ForbiddenPages";
import { AccessDeniedPage } from "@/lib/components/AccessDeniedPage";
import { SessionExpiredPage } from "@/lib/components/SessionExpiredPage";

export default function StatusPage() {
  const { state } = useApiCall("campaign-status", getCampaignStatus);
  useReportForbidden("/status", state.status === "forbidden");

  if (state.status === "unauthenticated") return <SessionExpiredPage />;
  if (state.status === "forbidden") {
    return <AccessDeniedPage message="No tienes permiso para ver el estado de las campañas." />;
  }

  return (
    <div>
      <h1>Estado de las campañas</h1>
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
      {state.status === "ready" && state.data.length > 0 && <StatusTable rows={state.data} />}
    </div>
  );
}
