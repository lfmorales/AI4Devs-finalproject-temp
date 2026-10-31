import { expect, type APIRequestContext, type Page } from "@playwright/test";

import { isoDate, lastDayOf, madridToday, type Month } from "./margin";

interface MasterItem {
  id: number;
  name: string;
  is_active?: boolean;
}

/** The option names the form's drop-downs get, chosen from the masters of the API. */
export interface MasterChoices {
  agency: string;
  advertiser: string;
  campaignType: string;
  sector: string;
  salesRep: string;
  dsp: string;
  channel: string;
  format: string;
}

/** The first name that starts with DEMO, or the first one when there is none. */
function preferDemo(items: MasterItem[], path: string): string {
  const usable = items.filter((item) => item.is_active !== false);
  const chosen = usable.find((item) => item.name.startsWith("DEMO")) ?? usable[0];
  if (chosen === undefined) throw new Error(`GET /api/${path} has no usable item: the masters are not loaded.`);
  return chosen.name;
}

async function choose(api: APIRequestContext, path: string): Promise<string> {
  return preferDemo((await (await api.get(path)).json()) as MasterItem[], path);
}

export async function readMasterChoices(api: APIRequestContext): Promise<MasterChoices> {
  return {
    agency: await choose(api, "masters/agencies"),
    advertiser: await choose(api, "masters/advertisers"),
    campaignType: await choose(api, "masters/campaign-types"),
    sector: await choose(api, "masters/sectors"),
    salesRep: await choose(api, "masters/sales-reps"),
    dsp: await choose(api, "masters/dsps"),
    channel: await choose(api, "masters/channels"),
    format: await choose(api, "masters/formats"),
  };
}

export function addMonths({ year, month }: Month, count: number): Month {
  const index = year * 12 + (month - 1) + count;
  return { year: Math.floor(index / 12), month: (index % 12) + 1 };
}

export const firstDayOf = ({ year, month }: Month): string => isoDate(year, month, 1);
export const lastDateOf = (month: Month): string => isoDate(month.year, month.month, lastDayOf(month));

/** A campaign name nobody else uses: there is no delete endpoint, and reset-data.sh removes these. */
export const uniqueCampaignName = (): string => `E2E-ALTA-${Date.now()}`;

export const todayInMadrid = (): string => {
  const { year, month, day } = madridToday();
  return isoDate(year, month, day);
};

export interface CampaignInput {
  name: string;
  start: string;
  end: string;
  impressions: number;
  cpm: string;
}

/** Fills the campaign and its only line. The label of every control is its accessible name. */
export async function fillCampaign(page: Page, masters: MasterChoices, input: CampaignInput): Promise<void> {
  await page.getByRole("textbox", { name: "Nombre de la campaña *", exact: true }).fill(input.name);
  await page.getByRole("textbox", { name: "Nombre mostrado *", exact: true }).fill(input.name);
  await page.getByRole("combobox", { name: "Agencia *", exact: true }).selectOption({ label: masters.agency });
  await page.getByRole("combobox", { name: "Anunciante *", exact: true }).selectOption({ label: masters.advertiser });
  await page.getByRole("combobox", { name: "Tipo de campaña *", exact: true }).selectOption({ label: masters.campaignType });
  await page.getByRole("combobox", { name: "Sector *", exact: true }).selectOption({ label: masters.sector });
  await page.getByRole("combobox", { name: "Comercial *", exact: true }).selectOption({ label: masters.salesRep });
  await page.getByLabel("Fecha de inicio *", { exact: true }).fill(input.start);
  await page.getByLabel("Fecha de fin *", { exact: true }).fill(input.end);
  await page.getByRole("textbox", { name: "Referencia de orden *", exact: true }).fill(input.name);
  await page.getByLabel("Fecha de recepción *", { exact: true }).fill(todayInMadrid());

  await page.getByRole("combobox", { name: "DSP *", exact: true }).selectOption({ label: masters.dsp });
  await page.getByRole("combobox", { name: "Canal *", exact: true }).selectOption({ label: masters.channel });
  await page.getByRole("combobox", { name: "Formato *", exact: true }).selectOption({ label: masters.format });
  await page.getByRole("combobox", { name: "Alcance *", exact: true }).selectOption({ label: "Nacional" });
  await page.getByRole("textbox", { name: "Descripción del mercado *", exact: true }).fill("E2E");
  await page.getByRole("spinbutton", { name: "Impresiones contratadas *", exact: true }).fill(String(input.impressions));
  await page.getByRole("textbox", { name: "CPM (venta) *", exact: true }).fill(input.cpm);
}

export async function openNewCampaign(page: Page): Promise<void> {
  await page.goto("/campaigns/new");
  await expect(page.getByRole("heading", { name: "Nueva campaña" })).toBeVisible();
  // The masters load after the first paint; the drop-downs hold only their placeholder until then.
  await expect(page.getByRole("combobox", { name: "Agencia *", exact: true }).getByRole("option")).not.toHaveCount(1);
}

export const calculateButton = (page: Page) => page.getByRole("button", { name: "Calcular reparto", exact: true });
export const submitButton = (page: Page) => page.getByRole("button", { name: "Registrar campaña", exact: true });
export const volumeFields = (page: Page) => page.getByRole("spinbutton", { name: /^Volumen \d{2}\/\d{4}$/ });
export const monthLabel = ({ year, month }: Month): string => `${String(month).padStart(2, "0")}/${year}`;

/** The volumes the preview table shows, in order, read from its inputs. */
export async function shownVolumes(page: Page): Promise<number[]> {
  return (await volumeFields(page).evaluateAll((inputs) => inputs.map((input) => Number((input as HTMLInputElement).value))));
}

/** Counts the registrations (POST /api/campaigns) the browser sends from now on. */
export function countRegistrations(page: Page): { count: () => number } {
  let sent = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/api/campaigns") sent += 1;
  });
  return { count: () => sent };
}

export function waitForRegistration(page: Page) {
  return page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname === "/api/campaigns");
}

export interface RegisteredFlight {
  period_year: number;
  period_month: number;
  contracted_impressions: number;
}

export interface RegisteredCampaign {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  lines: { contracted_impressions: number; flights: RegisteredFlight[] }[];
}
