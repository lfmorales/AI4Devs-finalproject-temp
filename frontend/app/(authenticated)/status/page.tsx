"use client";

import { StatusTable } from "@/features/status/StatusTable";
import { getCampaignStatus } from "@/lib/api/status";
import { useApiCall } from "@/lib/api/useApiCall";
import { AccessDeniedPage } from "@/lib/components/AccessDeniedPage";
import { SessionExpiredPage } from "@/lib/components/SessionExpiredPage";

export default function StatusPage() {
  const { state } = useApiCall("campaign-status", getCampaignStatus);

  if (state.status === "unauthenticated") return <SessionExpiredPage />;
  if (state.status === "forbidden") {
    return <AccessDeniedPage message="No tienes permiso para ver el estado de las campañas." />;
  }

  return (
    <div style={{ padding: "2rem" }}>
      <h1 style={{ fontSize: "1.875rem", fontWeight: "bold", marginBottom: "2rem" }}>Estado de las campañas</h1>
      {state.status === "loading" && <div role="status">Cargando estado…</div>}
      {state.status === "ready" && <StatusTable rows={state.data} />}
    </div>
  );
}
