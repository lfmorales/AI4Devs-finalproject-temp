"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { createApiClient, ApiError } from "@/lib/api/client";
import { LineDatesControl } from "./LineDatesControl";
import { createCampaignSchema, type CampaignCreateRequest } from "./schema";

interface MasterItem {
  id: number;
  name: string;
}

interface DSPItem extends MasterItem {
  is_active: boolean;
}

interface CampaignLine {
  id: string;
  dsp_id: number | "";
  channel_id: number | "";
  format_id: number | "";
  scope: "national" | "international" | "";
  market_description: string;
  contracted_impressions: string;
  sale_cpm: string;
  /** True: the line runs over the campaign's dates and sends none of its own. */
  inherit_dates: boolean;
  start_date: string;
  end_date: string;
}

interface FormData {
  name: string;
  display_name: string;
  agency_id: number | "";
  advertiser_id: number | "";
  campaign_type_id: number | "";
  sector_id: number | "";
  sales_rep_id: number | "";
  start_date: string;
  end_date: string;
  order_reference: string;
  order_received_on: string;
  lines: CampaignLine[];
}

interface CreateCampaignFormProps {
  onAuthError?: (kind: "unauthenticated" | "forbidden") => void;
}

export function CreateCampaignForm({ onAuthError }: CreateCampaignFormProps = {}) {
  const router = useRouter();
  const [masterData, setMasterData] = useState<{
    agencies: MasterItem[];
    advertisers: MasterItem[];
    campaignTypes: MasterItem[];
    sectors: MasterItem[];
    salesReps: MasterItem[];
    dsps: DSPItem[];
    channels: MasterItem[];
    formats: MasterItem[];
  }>({
    agencies: [],
    advertisers: [],
    campaignTypes: [],
    sectors: [],
    salesReps: [],
    dsps: [],
    channels: [],
    formats: [],
  });

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const [formData, setFormData] = useState<FormData>({
    name: "",
    display_name: "",
    agency_id: "",
    advertiser_id: "",
    campaign_type_id: "",
    sector_id: "",
    sales_rep_id: "",
    start_date: "",
    end_date: "",
    order_reference: "",
    order_received_on: "",
    lines: [
      {
        id: "line-0",
        dsp_id: "",
        channel_id: "",
        format_id: "",
        scope: "",
        market_description: "",
        contracted_impressions: "",
        sale_cpm: "",
        inherit_dates: true,
        start_date: "",
        end_date: "",
      },
    ],
  });

  // Load master data on mount
  useEffect(() => {
    async function loadMasterData() {
      try {
        setLoading(true);
        setLoadError(null);

        const baseUrl = process.env.NEXT_PUBLIC_API_URL;
        if (!baseUrl) {
          throw new Error("API URL not configured");
        }

        const client = createApiClient({ baseUrl });

        const [agencies, advertisers, campaignTypes, sectors, salesReps, dsps, channels, formats] =
          await Promise.all([
            client.get<MasterItem[]>("/masters/agencies"),
            client.get<MasterItem[]>("/masters/advertisers"),
            client.get<MasterItem[]>("/masters/campaign-types"),
            client.get<MasterItem[]>("/masters/sectors"),
            client.get<MasterItem[]>("/masters/sales-reps"),
            client.get<DSPItem[]>("/masters/dsps"),
            client.get<MasterItem[]>("/masters/channels"),
            client.get<MasterItem[]>("/masters/formats"),
          ]);

        setMasterData({
          agencies,
          advertisers,
          campaignTypes,
          sectors,
          salesReps,
          dsps,
          channels,
          formats,
        });
      } catch (err) {
        setLoadError("Error al cargar los datos maestros. Intenta de nuevo más tarde.");
      } finally {
        setLoading(false);
      }
    }

    void loadMasterData();
  }, []);

  const handleHeaderChange = useCallback((field: keyof Omit<FormData, "lines">, value: string | number) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
    // Clear field error when user starts typing
    if (fieldErrors[field]) {
      setFieldErrors((prev) => {
        const updated = { ...prev };
        delete updated[field];
        return updated;
      });
    }
  }, [fieldErrors]);

  const handleLineChange = (lineId: string, field: keyof CampaignLine, value: string | number | boolean) => {
    const lineIndex = formData.lines.findIndex((l) => l.id === lineId);
    setFormData((prev) => ({
      ...prev,
      lines: prev.lines.map((line) =>
        line.id === lineId ? { ...line, [field]: value } : line
      ),
    }));
    // Clear field error when user starts typing
    const fieldPath = `lines.${lineIndex}.${field}`;
    if (fieldErrors[fieldPath]) {
      setFieldErrors((prev) => {
        const updated = { ...prev };
        delete updated[fieldPath];
        return updated;
      });
    }
  };

  const addLine = () => {
    const newId = `line-${Date.now()}`;
    setFormData((prev) => ({
      ...prev,
      lines: [
        ...prev.lines,
        {
          id: newId,
          dsp_id: "",
          channel_id: "",
          format_id: "",
          scope: "",
          market_description: "",
          contracted_impressions: "",
          sale_cpm: "",
          inherit_dates: true,
          start_date: "",
          end_date: "",
        },
      ],
    }));
  };

  const removeLine = (lineId: string) => {
    if (formData.lines.length > 1) {
      setFormData((prev) => ({
        ...prev,
        lines: prev.lines.filter((line) => line.id !== lineId),
      }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (submitting) return;

    setSubmitting(true);
    setSubmitError(null);
    setFieldErrors({});

    try {
      // Convert form data to API format
      const campaignData = {
        name: formData.name,
        display_name: formData.display_name,
        agency_id: Number(formData.agency_id),
        advertiser_id: Number(formData.advertiser_id),
        campaign_type_id: Number(formData.campaign_type_id),
        sector_id: Number(formData.sector_id),
        sales_rep_id: Number(formData.sales_rep_id),
        start_date: formData.start_date,
        end_date: formData.end_date,
        order_reference: formData.order_reference,
        order_received_on: formData.order_received_on,
        lines: formData.lines.map((line) => ({
          dsp_id: Number(line.dsp_id),
          channel_id: Number(line.channel_id),
          format_id: Number(line.format_id),
          scope: line.scope,
          market_description: line.market_description,
          contracted_impressions: Number(line.contracted_impressions),
          sale_cpm: line.sale_cpm,
          // Own dates only when the line does not inherit the campaign's.
          ...(line.inherit_dates ? {} : { start_date: line.start_date, end_date: line.end_date }),
        })),
      };

      // Validate with schema using safeParse
      const validation = createCampaignSchema.safeParse(campaignData);
      if (!validation.success) {
        const fieldErrorsMap: Record<string, string> = {};

        for (const issue of validation.error.issues) {
          const fieldPath = issue.path.join(".");
          fieldErrorsMap[fieldPath] = issue.message;
        }

        setFieldErrors(fieldErrorsMap);
        if (Object.keys(fieldErrorsMap).length > 0) {
          setSubmitError("Por favor corrige los errores antes de enviar.");
          setSubmitting(false);
          return;
        }
      }

      // Submit to API
      const baseUrl = process.env.NEXT_PUBLIC_API_URL;
      if (!baseUrl) {
        throw new Error("API URL not configured");
      }

      const client = createApiClient({ baseUrl });
      await client.post("/campaigns", campaignData);

      // On success, redirect to campaigns list
      router.push("/campaigns?success=true");
    } catch (err) {
      // Check if it's an API error by checking for the kind property
      if (err && typeof err === 'object' && 'kind' in err && 'status' in err) {
        const apiError = err as ApiError;
        if (apiError.kind === "unauthenticated") {
          // Session expired - notify parent component
          onAuthError?.("unauthenticated");
          setSubmitError("Sesión caducada. Por favor, inicia sesión nuevamente.");
        } else if (apiError.kind === "forbidden") {
          // Access denied - notify parent component
          onAuthError?.("forbidden");
          setSubmitError("No tienes permiso para registrar campañas.");
        } else if (apiError.status === 409 && apiError.code === "duplicate_campaign_name") {
          // Duplicate campaign name - set error in the field
          setFieldErrors({
            name: "Esta campaña ya existe",
          });
          setSubmitError("Por favor corrige los errores antes de enviar.");
        } else if (apiError.status === 409 && apiError.code === "duplicate_order_reference") {
          // Duplicate order reference - set error in the field
          setFieldErrors({
            order_reference: "Esta referencia de orden ya existe",
          });
          setSubmitError("Por favor corrige los errores antes de enviar.");
        } else {
          setSubmitError(apiError.message);
          // Set field-specific errors from validation
          if (Object.keys(apiError.fieldErrors).length > 0) {
            setFieldErrors(apiError.fieldErrors);
          }
        }
      } else if (err instanceof Error) {
        // Never show raw validation error messages
        setSubmitError("Error al registrar la campaña. Intenta de nuevo más tarde.");
      } else {
        setSubmitError("Error al registrar la campaña. Intenta de nuevo más tarde.");
      }
    }
  };

  if (loading) {
    return <div role="status">Cargando formulario…</div>;
  }

  return (
    <form onSubmit={handleSubmit} style={{ maxWidth: "64rem", margin: "0 auto", padding: "2rem" }}>
      <h1 style={{ fontSize: "1.875rem", fontWeight: "bold", marginBottom: "2rem" }}>Nueva campaña</h1>

      {loadError && (
        <div style={{ backgroundColor: "#fee2e2", padding: "1rem", marginBottom: "1rem", borderRadius: "0.375rem", color: "#7f1d1d" }}>
          {loadError}
        </div>
      )}

      {submitError && (
        <div style={{ backgroundColor: "#fee2e2", padding: "1rem", marginBottom: "1rem", borderRadius: "0.375rem", color: "#7f1d1d" }}>
          {submitError}
        </div>
      )}

      {/* Header Section */}
      <fieldset style={{ marginBottom: "2rem", border: "none", padding: "0" }}>
        <legend style={{ fontSize: "1.125rem", fontWeight: "600", marginBottom: "1rem" }}>Información de la campaña</legend>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "1.5rem", marginBottom: "1.5rem" }}>
          <div>
            <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
              Nombre de la campaña *
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => handleHeaderChange("name", e.target.value)}
              style={{
                width: "100%",
                padding: "0.5rem",
                border: fieldErrors.name ? "2px solid #dc2626" : "1px solid #d1d5db",
                borderRadius: "0.375rem",
              }}
            />
            {fieldErrors.name && (
              <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors.name}</p>
            )}
          </div>

          <div>
            <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
              Nombre mostrado *
            </label>
            <input
              type="text"
              value={formData.display_name}
              onChange={(e) => handleHeaderChange("display_name", e.target.value)}
              style={{
                width: "100%",
                padding: "0.5rem",
                border: fieldErrors.display_name ? "2px solid #dc2626" : "1px solid #d1d5db",
                borderRadius: "0.375rem",
              }}
            />
            {fieldErrors.display_name && (
              <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors.display_name}</p>
            )}
          </div>

          <div>
            <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
              Agencia *
            </label>
            <select
              value={formData.agency_id}
              onChange={(e) => handleHeaderChange("agency_id", Number(e.target.value))}
              style={{
                width: "100%",
                padding: "0.5rem",
                border: fieldErrors.agency_id ? "2px solid #dc2626" : "1px solid #d1d5db",
                borderRadius: "0.375rem",
              }}
            >
              <option value="">Selecciona una agencia</option>
              {masterData.agencies.map((agency) => (
                <option key={agency.id} value={agency.id}>
                  {agency.name}
                </option>
              ))}
            </select>
            {fieldErrors.agency_id && (
              <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors.agency_id}</p>
            )}
          </div>

          <div>
            <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
              Anunciante *
            </label>
            <select
              value={formData.advertiser_id}
              onChange={(e) => handleHeaderChange("advertiser_id", Number(e.target.value))}
              style={{
                width: "100%",
                padding: "0.5rem",
                border: fieldErrors.advertiser_id ? "2px solid #dc2626" : "1px solid #d1d5db",
                borderRadius: "0.375rem",
              }}
            >
              <option value="">Selecciona un anunciante</option>
              {masterData.advertisers.map((advertiser) => (
                <option key={advertiser.id} value={advertiser.id}>
                  {advertiser.name}
                </option>
              ))}
            </select>
            {fieldErrors.advertiser_id && (
              <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors.advertiser_id}</p>
            )}
          </div>

          <div>
            <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
              Tipo de campaña *
            </label>
            <select
              value={formData.campaign_type_id}
              onChange={(e) => handleHeaderChange("campaign_type_id", Number(e.target.value))}
              style={{
                width: "100%",
                padding: "0.5rem",
                border: fieldErrors.campaign_type_id ? "2px solid #dc2626" : "1px solid #d1d5db",
                borderRadius: "0.375rem",
              }}
            >
              <option value="">Selecciona un tipo</option>
              {masterData.campaignTypes.map((type) => (
                <option key={type.id} value={type.id}>
                  {type.name}
                </option>
              ))}
            </select>
            {fieldErrors.campaign_type_id && (
              <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors.campaign_type_id}</p>
            )}
          </div>

          <div>
            <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
              Sector *
            </label>
            <select
              value={formData.sector_id}
              onChange={(e) => handleHeaderChange("sector_id", Number(e.target.value))}
              style={{
                width: "100%",
                padding: "0.5rem",
                border: fieldErrors.sector_id ? "2px solid #dc2626" : "1px solid #d1d5db",
                borderRadius: "0.375rem",
              }}
            >
              <option value="">Selecciona un sector</option>
              {masterData.sectors.map((sector) => (
                <option key={sector.id} value={sector.id}>
                  {sector.name}
                </option>
              ))}
            </select>
            {fieldErrors.sector_id && (
              <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors.sector_id}</p>
            )}
          </div>

          <div>
            <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
              Comercial *
            </label>
            <select
              value={formData.sales_rep_id}
              onChange={(e) => handleHeaderChange("sales_rep_id", Number(e.target.value))}
              style={{
                width: "100%",
                padding: "0.5rem",
                border: fieldErrors.sales_rep_id ? "2px solid #dc2626" : "1px solid #d1d5db",
                borderRadius: "0.375rem",
              }}
            >
              <option value="">Selecciona un comercial</option>
              {masterData.salesReps.map((rep) => (
                <option key={rep.id} value={rep.id}>
                  {rep.name}
                </option>
              ))}
            </select>
            {fieldErrors.sales_rep_id && (
              <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors.sales_rep_id}</p>
            )}
          </div>

          <div>
            <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
              Fecha de inicio *
            </label>
            <input
              type="date"
              value={formData.start_date}
              onChange={(e) => handleHeaderChange("start_date", e.target.value)}
              style={{
                width: "100%",
                padding: "0.5rem",
                border: fieldErrors.start_date ? "2px solid #dc2626" : "1px solid #d1d5db",
                borderRadius: "0.375rem",
              }}
            />
            {fieldErrors.start_date && (
              <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors.start_date}</p>
            )}
          </div>

          <div>
            <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
              Fecha de fin *
            </label>
            <input
              type="date"
              value={formData.end_date}
              onChange={(e) => handleHeaderChange("end_date", e.target.value)}
              style={{
                width: "100%",
                padding: "0.5rem",
                border: fieldErrors.end_date ? "2px solid #dc2626" : "1px solid #d1d5db",
                borderRadius: "0.375rem",
              }}
            />
            {fieldErrors.end_date && (
              <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors.end_date}</p>
            )}
          </div>

          <div>
            <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
              Referencia de orden *
            </label>
            <input
              type="text"
              value={formData.order_reference}
              onChange={(e) => handleHeaderChange("order_reference", e.target.value)}
              style={{
                width: "100%",
                padding: "0.5rem",
                border: fieldErrors.order_reference ? "2px solid #dc2626" : "1px solid #d1d5db",
                borderRadius: "0.375rem",
              }}
            />
            {fieldErrors.order_reference && (
              <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors.order_reference}</p>
            )}
          </div>

          <div>
            <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
              Fecha de recepción *
            </label>
            <input
              type="date"
              value={formData.order_received_on}
              onChange={(e) => handleHeaderChange("order_received_on", e.target.value)}
              style={{
                width: "100%",
                padding: "0.5rem",
                border: fieldErrors.order_received_on ? "2px solid #dc2626" : "1px solid #d1d5db",
                borderRadius: "0.375rem",
              }}
            />
            {fieldErrors.order_received_on && (
              <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors.order_received_on}</p>
            )}
          </div>
        </div>
      </fieldset>

      {/* Lines Section */}
      <fieldset style={{ marginBottom: "2rem", border: "none", padding: "0" }}>
        <legend style={{ fontSize: "1.125rem", fontWeight: "600", marginBottom: "1rem" }}>Líneas de campaña</legend>

        {formData.lines.map((line, lineIndex) => (
          <div key={line.id} style={{ marginBottom: "1.5rem", padding: "1rem", border: "1px solid #e5e7eb", borderRadius: "0.375rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <h3 style={{ fontSize: "1rem", fontWeight: "600" }}>Línea {lineIndex + 1}</h3>
              <button
                type="button"
                onClick={() => removeLine(line.id)}
                disabled={formData.lines.length === 1}
                style={{
                  padding: "0.5rem 1rem",
                  backgroundColor: formData.lines.length === 1 ? "#d1d5db" : "#dc2626",
                  color: "white",
                  borderRadius: "0.375rem",
                  border: "none",
                  cursor: formData.lines.length === 1 ? "not-allowed" : "pointer",
                  opacity: formData.lines.length === 1 ? 0.5 : 1,
                }}
              >
                Quitar línea
              </button>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "1.5rem" }}>
              <div>
                <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
                  DSP *
                </label>
                <select
                  value={line.dsp_id}
                  onChange={(e) => handleLineChange(line.id, "dsp_id", Number(e.target.value))}
                  style={{
                    width: "100%",
                    padding: "0.5rem",
                    border: fieldErrors[`lines.${lineIndex}.dsp_id`] ? "2px solid #dc2626" : "1px solid #d1d5db",
                    borderRadius: "0.375rem",
                  }}
                >
                  <option value="">Selecciona un DSP</option>
                  {masterData.dsps.map((dsp) => (
                    <option key={dsp.id} value={dsp.id}>
                      {dsp.name}
                    </option>
                  ))}
                </select>
                {fieldErrors[`lines.${lineIndex}.dsp_id`] && (
                  <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors[`lines.${lineIndex}.dsp_id`]}</p>
                )}
              </div>

              <div>
                <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
                  Canal *
                </label>
                <select
                  value={line.channel_id}
                  onChange={(e) => handleLineChange(line.id, "channel_id", Number(e.target.value))}
                  style={{
                    width: "100%",
                    padding: "0.5rem",
                    border: fieldErrors[`lines.${lineIndex}.channel_id`] ? "2px solid #dc2626" : "1px solid #d1d5db",
                    borderRadius: "0.375rem",
                  }}
                >
                  <option value="">Selecciona un canal</option>
                  {masterData.channels.map((channel) => (
                    <option key={channel.id} value={channel.id}>
                      {channel.name}
                    </option>
                  ))}
                </select>
                {fieldErrors[`lines.${lineIndex}.channel_id`] && (
                  <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors[`lines.${lineIndex}.channel_id`]}</p>
                )}
              </div>

              <div>
                <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
                  Formato *
                </label>
                <select
                  value={line.format_id}
                  onChange={(e) => handleLineChange(line.id, "format_id", Number(e.target.value))}
                  style={{
                    width: "100%",
                    padding: "0.5rem",
                    border: fieldErrors[`lines.${lineIndex}.format_id`] ? "2px solid #dc2626" : "1px solid #d1d5db",
                    borderRadius: "0.375rem",
                  }}
                >
                  <option value="">Selecciona un formato</option>
                  {masterData.formats.map((format) => (
                    <option key={format.id} value={format.id}>
                      {format.name}
                    </option>
                  ))}
                </select>
                {fieldErrors[`lines.${lineIndex}.format_id`] && (
                  <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors[`lines.${lineIndex}.format_id`]}</p>
                )}
              </div>

              <div>
                <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
                  Alcance *
                </label>
                <select
                  value={line.scope}
                  onChange={(e) => handleLineChange(line.id, "scope", e.target.value)}
                  style={{
                    width: "100%",
                    padding: "0.5rem",
                    border: fieldErrors[`lines.${lineIndex}.scope`] ? "2px solid #dc2626" : "1px solid #d1d5db",
                    borderRadius: "0.375rem",
                  }}
                >
                  <option value="">Selecciona alcance</option>
                  <option value="national">Nacional</option>
                  <option value="international">Internacional</option>
                </select>
                {fieldErrors[`lines.${lineIndex}.scope`] && (
                  <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors[`lines.${lineIndex}.scope`]}</p>
                )}
              </div>

              <div>
                <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
                  Descripción del mercado *
                </label>
                <input
                  type="text"
                  value={line.market_description}
                  onChange={(e) => handleLineChange(line.id, "market_description", e.target.value)}
                  style={{
                    width: "100%",
                    padding: "0.5rem",
                    border: fieldErrors[`lines.${lineIndex}.market_description`] ? "2px solid #dc2626" : "1px solid #d1d5db",
                    borderRadius: "0.375rem",
                  }}
                />
                {fieldErrors[`lines.${lineIndex}.market_description`] && (
                  <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors[`lines.${lineIndex}.market_description`]}</p>
                )}
              </div>

              <div>
                <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
                  Impresiones contratadas *
                </label>
                <input
                  type="number"
                  min="1"
                  value={line.contracted_impressions}
                  onChange={(e) => handleLineChange(line.id, "contracted_impressions", e.target.value)}
                  style={{
                    width: "100%",
                    padding: "0.5rem",
                    border: fieldErrors[`lines.${lineIndex}.contracted_impressions`] ? "2px solid #dc2626" : "1px solid #d1d5db",
                    borderRadius: "0.375rem",
                  }}
                />
                {fieldErrors[`lines.${lineIndex}.contracted_impressions`] && (
                  <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors[`lines.${lineIndex}.contracted_impressions`]}</p>
                )}
              </div>

              <div>
                <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: "500" }}>
                  CPM (venta) *
                </label>
                <input
                  type="text"
                  placeholder="0.00"
                  value={line.sale_cpm}
                  onChange={(e) => handleLineChange(line.id, "sale_cpm", e.target.value)}
                  style={{
                    width: "100%",
                    padding: "0.5rem",
                    border: fieldErrors[`lines.${lineIndex}.sale_cpm`] ? "2px solid #dc2626" : "1px solid #d1d5db",
                    borderRadius: "0.375rem",
                  }}
                />
                {fieldErrors[`lines.${lineIndex}.sale_cpm`] && (
                  <p style={{ color: "#dc2626", fontSize: "0.875rem", marginTop: "0.25rem" }}>{fieldErrors[`lines.${lineIndex}.sale_cpm`]}</p>
                )}
              </div>

              <LineDatesControl
                idPrefix={line.id}
                inherit={line.inherit_dates}
                startDate={line.start_date}
                endDate={line.end_date}
                startError={fieldErrors[`lines.${lineIndex}.start_date`]}
                endError={fieldErrors[`lines.${lineIndex}.end_date`]}
                onInheritChange={(inherit) => handleLineChange(line.id, "inherit_dates", inherit)}
                onDateChange={(field, value) => handleLineChange(line.id, field, value)}
              />
            </div>
          </div>
        ))}

        <button
          type="button"
          onClick={addLine}
          style={{
            padding: "0.5rem 1rem",
            backgroundColor: "#3b82f6",
            color: "white",
            borderRadius: "0.375rem",
            border: "none",
            cursor: "pointer",
            marginBottom: "1rem",
          }}
        >
          Añadir línea
        </button>

        {fieldErrors.lines && (
          <p style={{ color: "#dc2626", fontSize: "0.875rem" }}>{fieldErrors.lines}</p>
        )}
      </fieldset>

      {/* Submit Button */}
      <div style={{ display: "flex", gap: "1rem" }}>
        <button
          type="submit"
          disabled={submitting}
          style={{
            padding: "0.75rem 2rem",
            backgroundColor: submitting ? "#9ca3af" : "#10b981",
            color: "white",
            fontWeight: "600",
            borderRadius: "0.375rem",
            border: "none",
            cursor: submitting ? "not-allowed" : "pointer",
          }}
        >
          {submitting ? "Registrando…" : "Registrar campaña"}
        </button>

        <a
          href="/campaigns"
          style={{
            padding: "0.75rem 2rem",
            backgroundColor: "#6b7280",
            color: "white",
            fontWeight: "600",
            borderRadius: "0.375rem",
            textDecoration: "none",
            display: "inline-block",
          }}
        >
          Cancelar
        </a>
      </div>
    </form>
  );
}
