"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { createApiClient, type ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthContext";
import { useReportForbidden } from "@/lib/auth/ForbiddenPages";
import { SessionExpiredPage } from "@/lib/components/SessionExpiredPage";
import { AccessDeniedPage } from "@/lib/components/AccessDeniedPage";

interface Campaign {
  id: number;
  name: string;
  display_name: string;
  agency_id: number;
  advertiser_id: number;
  status: string;
  start_date: string;
  end_date: string;
}

type PageState = "list" | "session-expired" | "access-denied";

export default function CampaignsPage() {
  const { session } = useAuth();
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [pageState, setPageState] = useState<PageState>("list");

  useReportForbidden("/campaigns", pageState === "access-denied");

  useEffect(() => {
    async function loadCampaigns() {
      try {
        setLoading(true);
        setError(null);

        const baseUrl = process.env.NEXT_PUBLIC_API_URL;
        if (!baseUrl) {
          throw new Error("API URL not configured");
        }

        const client = createApiClient({ baseUrl });
        const data = await client.get<Campaign[]>("/campaigns");
        setCampaigns(data);
      } catch (err) {
        const apiError = err as ApiError;
        if (apiError.kind === "unauthenticated") {
          setPageState("session-expired");
        } else if (apiError.kind === "forbidden") {
          setPageState("access-denied");
        } else {
          setError("Error al cargar las campañas. Intenta de nuevo más tarde.");
          setCampaigns([]);
        }
      } finally {
        setLoading(false);
      }
    }

    if (session.status === "authenticated") {
      void loadCampaigns();
    }
  }, [session.status]);

  if (loading) {
    return <div role="status">Cargando campañas…</div>;
  }

  if (pageState === "session-expired") {
    return <SessionExpiredPage />;
  }

  if (pageState === "access-denied") {
    return <AccessDeniedPage message="No tienes permiso para ver las campañas." />;
  }

  return (
    <div>
      <div className="page-header">
        <h1>Campañas</h1>
        <div>
          <Link href="/campaigns/new">Nueva campaña</Link>
        </div>
      </div>

      {error && (
        <div style={{ backgroundColor: "#fee2e2", padding: "1rem", marginBottom: "1rem" }}>
          {error}
        </div>
      )}

      {campaigns && campaigns.length === 0 && !error && (
        <div style={{ textAlign: "center", padding: "3rem", backgroundColor: "#f3f4f6" }}>
          <p>Todavía no hay campañas registradas.</p>
          <p style={{ fontSize: "0.875rem", marginTop: "0.5rem" }}>
            Crea la primera campaña haciendo clic en "Nueva campaña".
          </p>
        </div>
      )}

      {campaigns && campaigns.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ backgroundColor: "#f3f4f6", borderBottom: "2px solid #d1d5db" }}>
              <th style={{ textAlign: "left", padding: "0.5rem 1rem", fontWeight: "600" }}>ID</th>
              <th style={{ textAlign: "left", padding: "0.5rem 1rem", fontWeight: "600" }}>Nombre</th>
              <th style={{ textAlign: "left", padding: "0.5rem 1rem", fontWeight: "600" }}>Nombre mostrado</th>
              <th style={{ textAlign: "left", padding: "0.5rem 1rem", fontWeight: "600" }}>Agencia</th>
              <th style={{ textAlign: "left", padding: "0.5rem 1rem", fontWeight: "600" }}>Anunciante</th>
              <th style={{ textAlign: "left", padding: "0.5rem 1rem", fontWeight: "600" }}>Estado</th>
              <th style={{ textAlign: "left", padding: "0.5rem 1rem", fontWeight: "600" }}>Inicio</th>
              <th style={{ textAlign: "left", padding: "0.5rem 1rem", fontWeight: "600" }}>Fin</th>
              <th style={{ textAlign: "left", padding: "0.5rem 1rem", fontWeight: "600" }}>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {campaigns.map((campaign) => (
              <tr key={campaign.id} style={{ borderBottom: "1px solid #e5e7eb" }}>
                <td style={{ padding: "0.5rem 1rem" }}>{campaign.id}</td>
                <td style={{ padding: "0.5rem 1rem" }}>{campaign.name}</td>
                <td style={{ padding: "0.5rem 1rem" }}>{campaign.display_name}</td>
                <td style={{ padding: "0.5rem 1rem" }}>{campaign.agency_id}</td>
                <td style={{ padding: "0.5rem 1rem" }}>{campaign.advertiser_id}</td>
                <td style={{ padding: "0.5rem 1rem" }}>{campaign.status}</td>
                <td style={{ padding: "0.5rem 1rem" }}>{campaign.start_date}</td>
                <td style={{ padding: "0.5rem 1rem" }}>{campaign.end_date}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
