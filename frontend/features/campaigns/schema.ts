import { z } from "zod";

/** Spanish texts of the line and flight rules. The backend codes with the same meaning are shown with these. */
export const FLIGHT_MESSAGES = {
  lineStartRequired: "Indica la fecha de inicio de la línea",
  lineEndRequired: "Indica la fecha de fin de la línea",
  lineStartOutside: "La fecha de inicio de la línea debe estar dentro de las fechas de la campaña.",
  lineEndOutside: "La fecha de fin de la línea debe estar dentro de las fechas de la campaña.",
  lineEndBeforeStart: "La fecha de fin de la línea no puede ser anterior a la de inicio.",
  datesOutside: "Las fechas de la línea deben estar dentro de las fechas de la campaña.",
  volumeTooSmall: "El volumen de la línea es demasiado pequeño para dar impresiones a todos los meses.",
  incomplete: "El reparto debe cubrir exactamente los meses en los que corre la línea.",
  notPositive: "Cada volumen mensual debe ser positivo.",
  mismatch: "Los volúmenes mensuales deben sumar el total de la línea.",
} as const;

export const monthlyVolumeSchema = z.object({
  year: z.number().int(),
  month: z.number().int().min(1).max(12),
  volume: z.number().int(),
});

export type MonthlyVolume = z.infer<typeof monthlyVolumeSchema>;

/**
 * The split a user typed, against the months the preview returned and the line's total.
 * Checked in the backend's order: coverage, then positivity, then the sum. Only the first failure is reported.
 */
export function manualVolumesSchema(months: { year: number; month: number }[], total: number) {
  return z.array(monthlyVolumeSchema).superRefine((volumes, ctx) => {
    const wanted = months.map((m) => `${m.year}-${m.month}`).sort();
    const given = volumes.map((v) => `${v.year}-${v.month}`).sort();
    if (wanted.length !== given.length || wanted.some((key, index) => key !== given[index])) {
      ctx.addIssue({ code: "custom", message: FLIGHT_MESSAGES.incomplete });
      return;
    }
    if (volumes.some((v) => v.volume <= 0)) {
      ctx.addIssue({ code: "custom", message: FLIGHT_MESSAGES.notPositive });
      return;
    }
    if (volumes.reduce((sum, v) => sum + v.volume, 0) !== total) {
      ctx.addIssue({ code: "custom", message: FLIGHT_MESSAGES.mismatch });
    }
  });
}

export interface LineDateIssue {
  field: "start_date" | "end_date";
  message: string;
}

const ISO_DATE = z.string().date();

/**
 * The problems of a line's own dates against the campaign's. Nothing is reported while the campaign's dates
 * cannot be compared with (invalid or inverted), because that is the campaign's own error.
 */
export function lineDateIssues(
  campaign: { start_date: string; end_date: string },
  line: { start_date?: string; end_date?: string },
): LineDateIssue[] {
  const issues: LineDateIssue[] = [];
  const hasStart = line.start_date !== undefined;
  const hasEnd = line.end_date !== undefined;
  if (!hasStart && !hasEnd) return issues;
  if (!hasStart) issues.push({ field: "start_date", message: FLIGHT_MESSAGES.lineStartRequired });
  if (!hasEnd) issues.push({ field: "end_date", message: FLIGHT_MESSAGES.lineEndRequired });

  const campaignComparable =
    ISO_DATE.safeParse(campaign.start_date).success &&
    ISO_DATE.safeParse(campaign.end_date).success &&
    campaign.start_date <= campaign.end_date;
  if (!campaignComparable) return issues;

  // ISO dates compare correctly as text.
  if (line.start_date !== undefined && (line.start_date < campaign.start_date || line.start_date > campaign.end_date)) {
    issues.push({ field: "start_date", message: FLIGHT_MESSAGES.lineStartOutside });
  }
  if (line.end_date !== undefined && (line.end_date < campaign.start_date || line.end_date > campaign.end_date)) {
    issues.push({ field: "end_date", message: FLIGHT_MESSAGES.lineEndOutside });
  }
  if (line.start_date !== undefined && line.end_date !== undefined && line.end_date < line.start_date) {
    issues.push({ field: "end_date", message: FLIGHT_MESSAGES.lineEndBeforeStart });
  }
  return issues;
}

const CPM_FORMAT = /^\d+(\.\d{1,2})?$/;
const NEGATIVE_NUMBER = /^-\s*\d/;

export const campaignLineSchema = z.object({
  dsp_id: z.number().int(),
  channel_id: z.number().int(),
  format_id: z.number().int(),
  scope: z.string().superRefine((val, ctx) => {
    if (!["national", "international"].includes(val)) {
      ctx.addIssue({
        code: "custom",
        message: "Selecciona el ámbito",
      });
    }
  }),
  market_description: z.string().min(1, "Descripción del mercado es obligatoria"),
  contracted_impressions: z.number().int().gt(0, "Impresiones contratadas debe ser mayor que 0"),
  // A sale CPM of 0 is a line without a price; it is never negative. The volume above stays above 0.
  sale_cpm: z.string().superRefine((value, ctx) => {
    if (NEGATIVE_NUMBER.test(value)) {
      ctx.addIssue({ code: "custom", message: "El CPM (venta) no puede ser negativo" });
    } else if (!CPM_FORMAT.test(value)) {
      ctx.addIssue({ code: "custom", message: "CPM (venta) debe ser un número decimal válido" });
    }
  }),
  // Sent only when the line does not inherit the campaign's dates.
  start_date: z.string().date("Fecha de inicio de la línea debe ser una fecha válida").optional(),
  end_date: z.string().date("Fecha de fin de la línea debe ser una fecha válida").optional(),
  // Sent only for a manual split.
  monthly_volumes: z.array(monthlyVolumeSchema).optional(),
});

export const createCampaignSchema = z.object({
  name: z.string().min(1, "Nombre de la campaña es obligatorio").max(255, "Nombre de la campaña no puede exceder 255 caracteres"),
  display_name: z.string().min(1, "Nombre mostrado es obligatorio").max(255, "Nombre mostrado no puede exceder 255 caracteres"),
  agency_id: z.number().int(),
  advertiser_id: z.number().int(),
  campaign_type_id: z.number().int(),
  sector_id: z.number().int(),
  sales_rep_id: z.number().int(),
  start_date: z.string().date("Fecha de inicio debe ser una fecha válida"),
  end_date: z.string().date("Fecha de fin debe ser una fecha válida"),
  order_reference: z.string().min(1, "Referencia de orden es obligatoria").max(255, "Referencia de orden no puede exceder 255 caracteres"),
  order_received_on: z.string().date("Fecha de recepción debe ser una fecha válida"),
  lines: z.array(campaignLineSchema).min(1, "Debe haber al menos una línea"),
}).refine((data) => new Date(data.start_date) <= new Date(data.end_date), {
  message: "Fecha de fin debe ser posterior o igual a fecha de inicio",
  path: ["end_date"],
}).superRefine((data, ctx) => {
  data.lines.forEach((line, index) => {
    for (const issue of lineDateIssues(data, line)) {
      ctx.addIssue({ code: "custom", message: issue.message, path: ["lines", index, issue.field] });
    }
  });
});

export type CampaignCreateRequest = z.infer<typeof createCampaignSchema>;
export type CampaignLineRequest = z.infer<typeof campaignLineSchema>;
