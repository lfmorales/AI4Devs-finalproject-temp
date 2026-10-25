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
    <div style={{ padding: "2rem" }}>
      <h1 style={{ fontSize: "1.875rem", fontWeight: "bold", marginBottom: "2rem" }}>Estado de las campañas</h1>
      {state.status === "loading" && <div role="status">Cargando estado…</div>}
      {state.status === "error" && (
        <div role="alert" style={{ backgroundColor: "#fee2e2", padding: "1rem" }}>
          No se pudo cargar el estado de las campañas. Inténtalo de nuevo más tarde.
        </div>
      )}
      {state.status === "ready" && state.data.length === 0 && (
        <div style={{ textAlign: "center", padding: "3rem", backgroundColor: "#f3f4f6" }}>
          <p>No hay campañas en curso</p>
        </div>
      )}
      {state.status === "ready" && state.data.length > 0 && <StatusTable rows={state.data} />}
    </div>
  );
}
