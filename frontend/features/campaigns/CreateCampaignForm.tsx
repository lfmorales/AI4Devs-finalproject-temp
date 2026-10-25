"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { createApiClient, ApiError } from "@/lib/api/client";
import { previewFlights } from "@/lib/api/flights";
import { lineErrorMessage, registrationLineErrors } from "./error-messages";
import { FlightEditor } from "./FlightEditor";
import { LineDatesControl } from "./LineDatesControl";
import {
  editVolume,
  isStale,
  manualSplitProblem,
  monthlyVolumesOf,
  newPreview,
  previewRequestFor,
  resetToProportional,
  type LinePreview,
} from "./line-flights";
import { createCampaignSchema, type CampaignCreateRequest } from "./schema";

type PreviewOutcome =
  | { ok: true; id: string; preview: LinePreview }
  | { ok: false; id: string; error: unknown };

const STALE_PREVIEW_MESSAGE = "Las fechas o el volumen han cambiado: vuelve a calcular el reparto.";
const GENERIC_PREVIEW_ERROR = "No se pudo calcular el reparto. Inténtalo de nuevo.";

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
  /** The last «Calcular reparto» result; stale as soon as the dates or the volume stop matching it. */
  preview: LinePreview | null;
  calculating: boolean;
  previewError: string | null;
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
        preview: null,
        calculating: false,
        previewError: null,
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

  const handleLineChange = (lineId: string, field: "dsp_id" | "channel_id" | "format_id" | "scope" | "market_description" | "contracted_impressions" | "sale_cpm" | "inherit_dates" | "start_date" | "end_date", value: string | number | boolean) => {
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

  const updateLine = (lineId: string, change: (line: CampaignLine) => CampaignLine) => {
    setFormData((prev) => ({ ...prev, lines: prev.lines.map((line) => (line.id === lineId ? change(line) : line)) }));
  };

  /** The request «Calcular reparto» would send for a line, or null while its inputs are not valid. */
  const requestFor = (line: CampaignLine) =>
    previewRequestFor({
      campaignStart: formData.start_date,
      campaignEnd: formData.end_date,
      inheritDates: line.inherit_dates,
      lineStart: line.start_date,
      lineEnd: line.end_date,
      total: line.contracted_impressions,
    });

  /** What the error mapping needs to know about each line. */
  const lineKinds = () =>
    formData.lines.map((line) => ({
      id: line.id,
      hasOwnDates: !line.inherit_dates,
      isManual: Boolean(line.preview?.manual && !isStale(line.preview, requestFor(line))),
    }));

  const calculateSplit = async (lineId: string) => {
    const line = formData.lines.find((l) => l.id === lineId);
    const request = line ? requestFor(line) : null;
    if (!line || !request) return;

    updateLine(lineId, (l) => ({ ...l, calculating: true, previewError: null }));
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL;
      if (!baseUrl) throw new Error("API URL not configured");
      const response = await previewFlights(createApiClient({ baseUrl }), request);
      updateLine(lineId, (l) => ({ ...l, calculating: false, preview: newPreview(request, response.flights) }));
    } catch (err) {
      const apiError = err && typeof err === "object" && "kind" in err ? (err as ApiError) : null;
      if (apiError?.kind === "unauthenticated") onAuthError?.("unauthenticated");
      if (apiError?.kind === "forbidden") onAuthError?.("forbidden");
      const message = lineErrorMessage(apiError?.code) ?? GENERIC_PREVIEW_ERROR;
      updateLine(lineId, (l) => ({ ...l, calculating: false, preview: null, previewError: message }));
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
          preview: null,
          calculating: false,
          previewError: null,
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
      // A split is sent only when the user edited it (manual) and it still matches the form.
      const currentManual = (line: CampaignLine) =>
        line.preview?.manual && !isStale(line.preview, requestFor(line)) ? line.preview : null;

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
        lines: formData.lines.map((line) => {
          const manual = currentManual(line);
          return {
            dsp_id: Number(line.dsp_id),
            channel_id: Number(line.channel_id),
            format_id: Number(line.format_id),
            scope: line.scope,
            market_description: line.market_description,
            contracted_impressions: Number(line.contracted_impressions),
            sale_cpm: line.sale_cpm,
            // Own dates only when the line does not inherit the campaign's.
            ...(line.inherit_dates ? {} : { start_date: line.start_date, end_date: line.end_date }),
            ...(manual ? { monthly_volumes: monthlyVolumesOf(manual) } : {}),
          };
        }),
      };

      // Validate with schema using safeParse
      const validation = createCampaignSchema.safeParse(campaignData);
      const fieldErrorsMap: Record<string, string> = {};
      if (!validation.success) {
        for (const issue of validation.error.issues) {
          fieldErrorsMap[issue.path.join(".")] = issue.message;
        }
      }

      // A manual split is checked against the months of its own preview; a stale one is never sent.
      const lineProblems: Record<string, string> = {};
      for (const line of formData.lines) {
        if (!line.preview?.manual) continue;
        lineProblems[line.id] = isStale(line.preview, requestFor(line))
          ? STALE_PREVIEW_MESSAGE
          : (manualSplitProblem(line.preview) ?? "");
      }
      const blockedLines = Object.entries(lineProblems).filter(([, message]) => message !== "");

      if (Object.keys(fieldErrorsMap).length > 0 || blockedLines.length > 0) {
        setFieldErrors(fieldErrorsMap);
        setFormData((prev) => ({
          ...prev,
          lines: prev.lines.map((line) => ({ ...line, previewError: lineProblems[line.id] || null })),
        }));
        setSubmitError("Por favor corrige los errores antes de enviar.");
        return;
      }

      // Every line without a current preview is previewed now, silently. The request is per line, so a
      // failure belongs to exactly that line. The registration goes out only if all of them pass.
      const baseUrl = process.env.NEXT_PUBLIC_API_URL;
      if (!baseUrl) {
        throw new Error("API URL not configured");
      }
      const client = createApiClient({ baseUrl });

      const needPreview = formData.lines.filter(
        (line) => !line.preview || isStale(line.preview, requestFor(line)),
      );
      const outcomes: PreviewOutcome[] = await Promise.all(
        needPreview.map(async (line) => {
          const request = requestFor(line);
          if (!request) return { ok: false, id: line.id, error: new Error("invalid preview inputs") };
          try {
            const response = await previewFlights(client, request);
            return { ok: true, id: line.id, preview: newPreview(request, response.flights) };
          } catch (error) {
            return { ok: false, id: line.id, error };
          }
        }),
      );

      const failures = outcomes.filter((outcome) => !outcome.ok);
      const authFailure = failures
        .map((outcome) => (outcome.ok ? {} : (outcome.error as Partial<ApiError>)))
        .find((error) => error.kind === "unauthenticated" || error.kind === "forbidden");
      if (authFailure) {
        // The page takes over (session expired / access denied).
        throw authFailure;
      }
      setFormData((prev) => ({
        ...prev,
        lines: prev.lines.map((line) => {
          const outcome = outcomes.find((o) => o.id === line.id);
          if (!outcome) return { ...line, previewError: null };
          if (outcome.ok) return { ...line, preview: outcome.preview, previewError: null };
          const code = (outcome.error as Partial<ApiError>).code;
          return { ...line, previewError: lineErrorMessage(code) ?? GENERIC_PREVIEW_ERROR };
        }),
      }));
      if (failures.length > 0) {
        setSubmitError("Por favor corrige los errores antes de enviar.");
        return;
      }

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
        } else if (apiError.status === 422 && registrationLineErrors(apiError.code, lineKinds()) !== null) {
          // The code names no line: it is shown on the lines that can have caused it, or on the form.
          const placement = registrationLineErrors(apiError.code, lineKinds())!;
          setFormData((prev) => ({
            ...prev,
            lines: prev.lines.map((line) => ({ ...line, previewError: placement.byLine[line.id] ?? null })),
          }));
          setSubmitError(placement.formLevel ?? "Por favor corrige los errores antes de enviar.");
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
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <div role="status">Cargando formulario…</div>;
  }

  return (
    <form className="campaign-form" onSubmit={handleSubmit}>
      <h1>Nueva campaña</h1>

      {loadError && (
        <div className="notice notice-error">
          {loadError}
        </div>
      )}

      {submitError && (
        <div className="notice notice-error">
          {submitError}
        </div>
      )}

      {/* Header Section */}
      <fieldset>
        <legend>Información de la campaña</legend>

        <div className="form-grid">
          <div>
            <label>
              Nombre de la campaña *
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => handleHeaderChange("name", e.target.value)}
            />
            {fieldErrors.name && (
              <p className="field-error">{fieldErrors.name}</p>
            )}
          </div>

          <div>
            <label>
              Nombre mostrado *
            </label>
            <input
              type="text"
              value={formData.display_name}
              onChange={(e) => handleHeaderChange("display_name", e.target.value)}
            />
            {fieldErrors.display_name && (
              <p className="field-error">{fieldErrors.display_name}</p>
            )}
          </div>

          <div>
            <label>
              Agencia *
            </label>
            <select
              value={formData.agency_id}
              onChange={(e) => handleHeaderChange("agency_id", Number(e.target.value))}
            >
              <option value="">Selecciona una agencia</option>
              {masterData.agencies.map((agency) => (
                <option key={agency.id} value={agency.id}>
                  {agency.name}
                </option>
              ))}
            </select>
            {fieldErrors.agency_id && (
              <p className="field-error">{fieldErrors.agency_id}</p>
            )}
          </div>

          <div>
            <label>
              Anunciante *
            </label>
            <select
              value={formData.advertiser_id}
              onChange={(e) => handleHeaderChange("advertiser_id", Number(e.target.value))}
            >
              <option value="">Selecciona un anunciante</option>
              {masterData.advertisers.map((advertiser) => (
                <option key={advertiser.id} value={advertiser.id}>
                  {advertiser.name}
                </option>
              ))}
            </select>
            {fieldErrors.advertiser_id && (
              <p className="field-error">{fieldErrors.advertiser_id}</p>
            )}
          </div>

          <div>
            <label>
              Tipo de campaña *
            </label>
            <select
              value={formData.campaign_type_id}
              onChange={(e) => handleHeaderChange("campaign_type_id", Number(e.target.value))}
            >
              <option value="">Selecciona un tipo</option>
              {masterData.campaignTypes.map((type) => (
                <option key={type.id} value={type.id}>
                  {type.name}
                </option>
              ))}
            </select>
            {fieldErrors.campaign_type_id && (
              <p className="field-error">{fieldErrors.campaign_type_id}</p>
            )}
          </div>

          <div>
            <label>
              Sector *
            </label>
            <select
              value={formData.sector_id}
              onChange={(e) => handleHeaderChange("sector_id", Number(e.target.value))}
            >
              <option value="">Selecciona un sector</option>
              {masterData.sectors.map((sector) => (
                <option key={sector.id} value={sector.id}>
                  {sector.name}
                </option>
              ))}
            </select>
            {fieldErrors.sector_id && (
              <p className="field-error">{fieldErrors.sector_id}</p>
            )}
          </div>

          <div>
            <label>
              Comercial *
            </label>
            <select
              value={formData.sales_rep_id}
              onChange={(e) => handleHeaderChange("sales_rep_id", Number(e.target.value))}
            >
              <option value="">Selecciona un comercial</option>
              {masterData.salesReps.map((rep) => (
                <option key={rep.id} value={rep.id}>
                  {rep.name}
                </option>
              ))}
            </select>
            {fieldErrors.sales_rep_id && (
              <p className="field-error">{fieldErrors.sales_rep_id}</p>
            )}
          </div>

          <div>
            <label>
              Fecha de inicio *
            </label>
            <input
              type="date"
              value={formData.start_date}
              onChange={(e) => handleHeaderChange("start_date", e.target.value)}
            />
            {fieldErrors.start_date && (
              <p className="field-error">{fieldErrors.start_date}</p>
            )}
          </div>

          <div>
            <label>
              Fecha de fin *
            </label>
            <input
              type="date"
              value={formData.end_date}
              onChange={(e) => handleHeaderChange("end_date", e.target.value)}
            />
            {fieldErrors.end_date && (
              <p className="field-error">{fieldErrors.end_date}</p>
            )}
          </div>

          <div>
            <label>
              Referencia de orden *
            </label>
            <input
              type="text"
              value={formData.order_reference}
              onChange={(e) => handleHeaderChange("order_reference", e.target.value)}
            />
            {fieldErrors.order_reference && (
              <p className="field-error">{fieldErrors.order_reference}</p>
            )}
          </div>

          <div>
            <label>
              Fecha de recepción *
            </label>
            <input
              type="date"
              value={formData.order_received_on}
              onChange={(e) => handleHeaderChange("order_received_on", e.target.value)}
            />
            {fieldErrors.order_received_on && (
              <p className="field-error">{fieldErrors.order_received_on}</p>
            )}
          </div>
        </div>
      </fieldset>

      {/* Lines Section */}
      <fieldset>
        <legend>Líneas de campaña</legend>

        {formData.lines.map((line, lineIndex) => (
          <div key={line.id} className="line-card">
            <div className="line-card-header">
              <h3>Línea {lineIndex + 1}</h3>
              <button
                type="button"
                className="btn-danger"
                onClick={() => removeLine(line.id)}
                disabled={formData.lines.length === 1}
              >
                Quitar línea
              </button>
            </div>

            <div className="form-grid">
              <div>
                <label>
                  DSP *
                </label>
                <select
                  value={line.dsp_id}
                  onChange={(e) => handleLineChange(line.id, "dsp_id", Number(e.target.value))}
                >
                  <option value="">Selecciona un DSP</option>
                  {masterData.dsps.map((dsp) => (
                    <option key={dsp.id} value={dsp.id}>
                      {dsp.name}
                    </option>
                  ))}
                </select>
                {fieldErrors[`lines.${lineIndex}.dsp_id`] && (
                  <p className="field-error">{fieldErrors[`lines.${lineIndex}.dsp_id`]}</p>
                )}
              </div>

              <div>
                <label>
                  Canal *
                </label>
                <select
                  value={line.channel_id}
                  onChange={(e) => handleLineChange(line.id, "channel_id", Number(e.target.value))}
                >
                  <option value="">Selecciona un canal</option>
                  {masterData.channels.map((channel) => (
                    <option key={channel.id} value={channel.id}>
                      {channel.name}
                    </option>
                  ))}
                </select>
                {fieldErrors[`lines.${lineIndex}.channel_id`] && (
                  <p className="field-error">{fieldErrors[`lines.${lineIndex}.channel_id`]}</p>
                )}
              </div>

              <div>
                <label>
                  Formato *
                </label>
                <select
                  value={line.format_id}
                  onChange={(e) => handleLineChange(line.id, "format_id", Number(e.target.value))}
                >
                  <option value="">Selecciona un formato</option>
                  {masterData.formats.map((format) => (
                    <option key={format.id} value={format.id}>
                      {format.name}
                    </option>
                  ))}
                </select>
                {fieldErrors[`lines.${lineIndex}.format_id`] && (
                  <p className="field-error">{fieldErrors[`lines.${lineIndex}.format_id`]}</p>
                )}
              </div>

              <div>
                <label>
                  Alcance *
                </label>
                <select
                  value={line.scope}
                  onChange={(e) => handleLineChange(line.id, "scope", e.target.value)}
                >
                  <option value="">Selecciona alcance</option>
                  <option value="national">Nacional</option>
                  <option value="international">Internacional</option>
                </select>
                {fieldErrors[`lines.${lineIndex}.scope`] && (
                  <p className="field-error">{fieldErrors[`lines.${lineIndex}.scope`]}</p>
                )}
              </div>

              <div>
                <label>
                  Descripción del mercado *
                </label>
                <input
                  type="text"
                  value={line.market_description}
                  onChange={(e) => handleLineChange(line.id, "market_description", e.target.value)}
                />
                {fieldErrors[`lines.${lineIndex}.market_description`] && (
                  <p className="field-error">{fieldErrors[`lines.${lineIndex}.market_description`]}</p>
                )}
              </div>

              <div>
                <label>
                  Impresiones contratadas *
                </label>
                <input
                  type="number"
                  min="1"
                  value={line.contracted_impressions}
                  onChange={(e) => handleLineChange(line.id, "contracted_impressions", e.target.value)}
                />
                {fieldErrors[`lines.${lineIndex}.contracted_impressions`] && (
                  <p className="field-error">{fieldErrors[`lines.${lineIndex}.contracted_impressions`]}</p>
                )}
              </div>

              <div>
                <label>
                  CPM (venta) *
                </label>
                <input
                  type="text"
                  placeholder="0.00"
                  value={line.sale_cpm}
                  onChange={(e) => handleLineChange(line.id, "sale_cpm", e.target.value)}
                />
                {fieldErrors[`lines.${lineIndex}.sale_cpm`] && (
                  <p className="field-error">{fieldErrors[`lines.${lineIndex}.sale_cpm`]}</p>
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

              <FlightEditor
                canCalculate={requestFor(line) !== null}
                calculating={line.calculating}
                preview={line.preview && !isStale(line.preview, requestFor(line)) ? line.preview : null}
                stale={line.preview !== null && isStale(line.preview, requestFor(line))}
                error={line.previewError}
                onCalculate={() => void calculateSplit(line.id)}
                onEditVolume={(index, value) =>
                  updateLine(line.id, (l) => (l.preview ? { ...l, preview: editVolume(l.preview, index, value) } : l))
                }
                onReset={() =>
                  updateLine(line.id, (l) => (l.preview ? { ...l, preview: resetToProportional(l.preview) } : l))
                }
              />
            </div>
          </div>
        ))}

        <button
          type="button"
          onClick={addLine}
        >
          Añadir línea
        </button>

        {fieldErrors.lines && (
          <p className="field-error">{fieldErrors.lines}</p>
        )}
      </fieldset>

      {/* Submit Button */}
      <div className="form-actions">
        <button
          type="submit"
          className="btn-primary"
          disabled={submitting}
        >
          {submitting ? "Registrando…" : "Registrar campaña"}
        </button>

        <a
          className="btn"
          href="/campaigns"
        >
          Cancelar
        </a>
      </div>
    </form>
  );
}
