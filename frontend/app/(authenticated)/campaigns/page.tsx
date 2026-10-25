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
    return <div role="status" className="notice notice-info">Cargando campañas…</div>;
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
          <Link className="btn btn-primary" href="/campaigns/new">Nueva campaña</Link>
        </div>
      </div>

      {error && (
        <div className="notice notice-error">
          {error}
        </div>
      )}

      {campaigns && campaigns.length === 0 && !error && (
        <div className="empty-state">
          <p>Todavía no hay campañas registradas.</p>
          <p>
            Crea la primera campaña haciendo clic en "Nueva campaña".
          </p>
        </div>
      )}

      {campaigns && campaigns.length > 0 && (
        <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th className="num">ID</th>
              <th>Nombre</th>
              <th>Nombre mostrado</th>
              <th>Agencia</th>
              <th>Anunciante</th>
              <th>Estado</th>
              <th>Inicio</th>
              <th>Fin</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {campaigns.map((campaign) => (
              <tr key={campaign.id}>
                <td className="num">{campaign.id}</td>
                <td>{campaign.name}</td>
                <td>{campaign.display_name}</td>
                <td>{campaign.agency_id}</td>
                <td>{campaign.advertiser_id}</td>
                <td>{campaign.status}</td>
                <td>{campaign.start_date}</td>
                <td>{campaign.end_date}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </div>
  );
}
