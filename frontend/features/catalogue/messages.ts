import type { IdentifierCheck } from "@/lib/api/dsp-catalog";

/** What Adform said when the pair was checked at the moment of linking. */
export const VALIDATION_MESSAGES: Record<IdentifierCheck, string> = {
  found: "Adform confirma la pareja.",
  unknown: "Adform no reconoce esta pareja.",
  unreachable: "No se pudo consultar Adform para validar la pareja.",
};

export const NO_RECENT_DELIVERY = "No consta entrega reciente de esta pareja";

/** Backend error codes of creating a mapping, in Spanish. The backend's own text is never shown. */
export const MAPPING_ERROR_MESSAGES: Record<string, string> = {
  duplicate_dsp_mapping: "Esta pareja de identificadores ya está vinculada a una línea.",
  campaign_line_not_found: "La línea elegida ya no existe.",
  dsp_not_supported: "El DSP de la línea elegida todavía no tiene conector.",
};

export const MAPPING_FAILED_MESSAGE = "No se pudo vincular la pareja. Inténtalo de nuevo.";
