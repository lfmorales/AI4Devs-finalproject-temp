import type { IdentifierCheck } from "@/lib/api/dsp-catalog";

/** What the DSP said when the pair was checked at the moment of linking; Equativ is never asked. */
export const VALIDATION_MESSAGES: Record<IdentifierCheck, string> = {
  found: "Adform confirma la pareja.",
  unknown: "Adform no reconoce esta pareja.",
  unreachable: "No se pudo consultar Adform para validar la pareja.",
  user_validated: "Validado por el usuario: no se consulta a Equativ al vincular.",
};

export const NO_RECENT_DELIVERY = "No consta entrega reciente de esta pareja";

/** Backend error codes of creating a mapping, in Spanish. The backend's own text is never shown. */
export const MAPPING_ERROR_MESSAGES: Record<string, string> = {
  duplicate_dsp_mapping: "Esta pareja de identificadores ya está vinculada a una línea.",
  campaign_line_not_found: "La línea elegida ya no existe.",
  dsp_not_supported: "El DSP de la línea elegida todavía no tiene conector.",
  invalid_equativ_package: "El identificador del paquete son solo cifras, sin ceros a la izquierda y mayor que cero, por ejemplo 900000001.",
};

/** The error that belongs to the package field itself, shown beside it. */
export const INVALID_EQUATIV_PACKAGE = "invalid_equativ_package";

export const NO_RECENT_PACKAGE_DELIVERY = "No consta entrega reciente de este paquete";

export function packageLinkedMessage(packageId: string, lineName: string): string {
  return `Paquete ${packageId} vinculado a ${lineName}.`;
}

export const MAPPING_FAILED_MESSAGE = "No se pudo vincular la pareja. Inténtalo de nuevo.";

/** Backend error codes of unlinking a line, in Spanish. The backend's own text is never shown. */
export const UNLINK_ERROR_MESSAGES: Record<string, string> = {
  ambiguous_mapping: "Esta línea tiene varias vinculaciones y no se puede desvincular desde aquí.",
  mapping_not_found: "La línea ya no tiene ninguna vinculación.",
  line_not_found: "La línea ya no existe.",
};

export const UNLINK_FAILED_MESSAGE = "No se pudo desvincular la pareja. Inténtalo de nuevo.";

/** Codes after which the pair is certainly not linked to a line any more. */
export function unlinkLeavesTheRowUnlinked(code: string | undefined): boolean {
  return code === "mapping_not_found";
}

export function removedDaysMessage(days: number): string {
  if (days === 0) return "Pareja desvinculada. No había días de entrega que retirar.";
  if (days === 1) return "Pareja desvinculada. Se retiró 1 día de entrega.";
  return `Pareja desvinculada. Se retiraron ${days} días de entrega.`;
}
