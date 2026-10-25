/** Backend error codes of the link call, in Spanish. The backend's own text is never shown. */
export const LINK_ERROR_MESSAGES: Record<string, string> = {
  exception_already_resolved: "Esta excepción ya estaba resuelta.",
  exception_not_found: "La excepción ya no existe.",
  exception_not_linkable: "Solo se puede vincular una excepción de entrega sin emparejar.",
  line_not_found: "La línea elegida ya no existe.",
  line_dsp_mismatch: "La línea elegida usa un DSP distinto al de esta excepción.",
  mapping_pair_taken: "Esta pareja de identificadores ya está vinculada a una línea.",
};

export const LINK_FAILED_MESSAGE = "No se pudo vincular la excepción. Inténtalo de nuevo.";

/** Codes after which the exception is certainly not open any more, so its row leaves the open queue. */
export function linkLeavesTheOpenQueue(code: string | undefined): boolean {
  return code === "exception_already_resolved" || code === "exception_not_found";
}

/** Shown after a link whose line began before the ingestion window. The browser offers no way to load it. */
export const HISTORY_LOAD_WARNING =
  "Esta línea empezó antes de la ventana de siete días. La entrega anterior no se carga sola: pide cargar el histórico con run_ingestion --from … --to …";

export const NO_CATALOGUE_NAME = "Sin nombre en el catálogo";
