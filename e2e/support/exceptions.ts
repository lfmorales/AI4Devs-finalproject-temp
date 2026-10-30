import type { APIRequestContext, Locator, Page } from "@playwright/test";

export type ExceptionType = "unmatched_delivery" | "missing_delivery" | "channel_mismatch";
export type ExceptionStatus = "open" | "resolved";

/** The parts of GET /api/ingestion-exceptions the specs read, as the backend's OpenAPI schema publishes them. */
export interface IngestionException {
  id: number;
  exception_type: ExceptionType;
  status: ExceptionStatus;
  dsp_id: number | null;
  external_campaign_id: string | null;
  external_line_item_id: string | null;
  campaign_line_id: number | null;
  note: string | null;
  campaign_name: string | null;
  line_item_name: string | null;
}

/** A line with no DSP mapping, as GET /api/campaign-lines/unmapped answers. */
export interface UnmappedLine {
  id: number;
  campaign_name: string;
  line_number: number;
  start_date: string;
  end_date: string;
  dsp_id: number;
  dsp_name: string;
}

interface CatalogItem {
  external_campaign_id: string;
  external_line_item_id: string;
  mapped_line_id: number | null;
}

/** The campaign that seed_exceptions_demo leaves with a line that has no mapping. */
export const LINK_TARGET_CAMPAIGN = "DEMO-EXC-CAMPANA";

export const TYPE_OPTION = { unmatched_delivery: "Entrega sin emparejar", missing_delivery: "Entrega ausente" } as const;
export const NO_MATCH_TEXT = "No hay excepciones que coincidan con la búsqueda";
export const ALREADY_RESOLVED = "Esta excepción ya estaba resuelta.";
export const GENERIC_RESOLVE_FAILURE = "No se pudo resolver la excepción. Inténtalo de nuevo.";
export const HISTORY_WARNING = "Esta línea empezó antes de la ventana de siete días.";

export async function readExceptions(api: APIRequestContext, status: ExceptionStatus): Promise<IngestionException[]> {
  const response = await api.get(`ingestion-exceptions?status=${status}`);
  if (response.status() !== 200) throw new Error(`GET /api/ingestion-exceptions?status=${status} answered ${response.status()}.`);
  return (await response.json()) as IngestionException[];
}

export async function readUnmappedLines(api: APIRequestContext): Promise<UnmappedLine[]> {
  const response = await api.get("campaign-lines/unmapped");
  if (response.status() !== 200) throw new Error(`GET /api/campaign-lines/unmapped answered ${response.status()}.`);
  return (await response.json()) as UnmappedLine[];
}

/**
 * The line the catalogue says a pair is mapped to, or null when no mapped item has that pair. The catalogue's `q`
 * filter searches the campaign and line names, not the identifiers, so this reads every mapped item, page by page,
 * and compares the pair as text.
 */
export async function mappedLineOf(api: APIRequestContext, externalCampaignId: string, externalLineItemId: string): Promise<number | null> {
  const limit = 200;
  for (let offset = 0; ; offset += limit) {
    const response = await api.get(`dsp-catalog?mapped=true&limit=${limit}&offset=${offset}`);
    if (response.status() !== 200) throw new Error(`GET /api/dsp-catalog answered ${response.status()}.`);
    const page = (await response.json()) as { items: CatalogItem[]; total: number };
    const item = page.items.find(
      (entry) => String(entry.external_campaign_id) === String(externalCampaignId) && String(entry.external_line_item_id) === String(externalLineItemId),
    );
    if (item !== undefined) return item.mapped_line_id;
    if (offset + limit >= page.total) return null;
  }
}

/** Lowercase without accents, as the screen's search compares. */
export function plain(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

/**
 * The open unmatched-delivery rows of the demonstration seed, oldest first. They are told apart from any real row by
 * the catalogue name the seed gives them ("DEMO Catalogo ...", with or without accents).
 */
export async function seededOpenUnmatched(api: APIRequestContext): Promise<IngestionException[]> {
  const open = await readExceptions(api, "open");
  return open
    .filter((row) => row.exception_type === "unmatched_delivery" && plain(row.line_item_name ?? "").startsWith("demo catalogo"))
    .sort((a, b) => a.id - b.id);
}

/** The unmapped line of the seeded link-target campaign, if the seed has not been used up yet. */
export async function seededLinkTarget(api: APIRequestContext): Promise<UnmappedLine | undefined> {
  return (await readUnmappedLines(api)).find((line) => line.campaign_name === LINK_TARGET_CAMPAIGN);
}

export function queueTable(page: Page): Locator {
  return page.getByRole("table", { name: "Cola de excepciones" });
}

/** The row of an exception, found by its own action button (open rows) or by the cells of the table (resolved). */
export function openRow(page: Page, exceptionId: number): Locator {
  return queueTable(page).getByRole("row").filter({ has: page.getByRole("button", { name: `Resolver excepción ${exceptionId}`, exact: true }) });
}

export async function openTab(page: Page, name: "Abiertas" | "Resueltas"): Promise<void> {
  await page.getByRole("tab", { name }).click();
}

export function searchBox(page: Page): Locator {
  return page.getByRole("searchbox", { name: "Buscar excepciones" });
}

export function typeSelect(page: Page): Locator {
  return page.getByRole("combobox", { name: "Tipo", exact: true });
}

/** The «Mostrando X de Y» counter, a plain paragraph read by its text. */
export function counter(page: Page, shown: number, total: number): Locator {
  return page.getByText(`Mostrando ${shown} de ${total}`, { exact: true });
}
