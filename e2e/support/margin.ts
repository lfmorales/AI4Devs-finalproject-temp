import { expect, type APIRequestContext, type Locator, type Page } from "@playwright/test";

import { formatDecimalEsEs } from "./format";

export type FlightState = "closed" | "pending_close" | "running";

/** The parts of GET /api/margin the specs read, as the backend's OpenAPI schema publishes them. */
export interface FlightMargin {
  flight_id: number;
  period_year: number;
  period_month: number;
  state: FlightState;
  below_cost: boolean;
  zero_sale: boolean;
  revenue: string;
  contracted_revenue: string;
  accrued_days: number;
  window_days: number;
  delivered_impressions: number;
  contracted_impressions: number;
  media_cost: string;
  rebate: string;
  platform_cost: string;
  margin: string;
  margin_pct: string | null;
}

interface Totals {
  revenue: string;
  contracted_revenue: string;
}

export interface LineMargin {
  line_number: number;
  flights: FlightMargin[];
}

export interface CampaignMargin {
  campaign_id: number;
  name: string;
  lines: LineMargin[];
  totals: Totals;
}

export interface MarginResponse {
  campaigns: CampaignMargin[];
}

export interface Month {
  year: number;
  month: number;
}

const MONTH_NAMES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const NO_BREAK_SPACE = " ";

export const FRESH_DATABASE_SKIP_REASON = "la base no está recién sembrada: ejecuta reset-data.sh";
export const NOTHING_TO_CLOSE = "No hay flights pendientes de cierre en este mes";
export const REMOVE_CAMPAIGN_FILTER = "Quita el filtro de campaña para cerrar el mes";

const STATE_LABEL: Record<FlightState, string> = {
  closed: "Cerrado",
  pending_close: "Pendiente de cierre",
  running: "En curso (provisional)",
};

export function monthName(month: number): string {
  return MONTH_NAMES[month - 1] ?? "";
}

export function monthOfYear({ year, month }: Month): string {
  return `${monthName(month)} de ${year}`;
}

/** Today in Madrid, where the application's calendar lives. */
export function madridToday(now: Date = new Date()): { year: number; month: number; day: number } {
  const [year = 0, month = 0, day = 0] = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Madrid" }).format(now).split("-").map(Number);
  return { year, month, day };
}

export function currentMonth(): Month {
  const { year, month } = madridToday();
  return { year, month };
}

/** The month the seeding leaves pending close: the one before today's. */
export function previousMonth(): Month {
  const { year, month } = currentMonth();
  return month === 1 ? { year: year - 1, month: 12 } : { year, month: month - 1 };
}

export function isoDate(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export function lastDayOf({ year, month }: Month): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

export const money = (value: string): string => `${formatDecimalEsEs(value)}${NO_BREAK_SPACE}€`;
export const percent = (value: string | null): string => (value === null ? "—" : `${formatDecimalEsEs(value)}${NO_BREAK_SPACE}%`);
export const integer = (value: number): string => formatDecimalEsEs(String(value));

export async function readMargin(api: APIRequestContext, month?: Month): Promise<MarginResponse> {
  const query = month === undefined ? "" : `?year=${month.year}&month=${month.month}`;
  const response = await api.get(`margin${query}`);
  expect(response.ok(), `GET /api/margin${query}`).toBe(true);
  return (await response.json()) as MarginResponse;
}

export function flightsOf(margin: MarginResponse): FlightMargin[] {
  return margin.campaigns.flatMap((campaign) => campaign.lines.flatMap((line) => line.flights));
}

export function hasPendingClose(margin: MarginResponse): boolean {
  return flightsOf(margin).some((flight) => flight.state === "pending_close");
}

/** What the closing of a month changes: the amounts of every flight, as strings, by flight. */
export function amountsByFlight(margin: MarginResponse): Record<number, string[]> {
  return Object.fromEntries(
    flightsOf(margin).map((flight) => [
      flight.flight_id,
      [flight.revenue, flight.contracted_revenue, flight.media_cost, flight.rebate, flight.platform_cost, flight.margin, flight.margin_pct ?? "null"],
    ]),
  );
}

export function closedFlightsMessage(closed: number, month: Month): string {
  if (closed === 1) return `Se cerró 1 flight de ${monthOfYear(month)}`;
  return `Se cerraron ${closed} flights de ${monthOfYear(month)}`;
}

export async function chooseMonth(page: Page, { year, month }: Month): Promise<void> {
  await page.getByLabel("Año").fill(String(year));
  await page.getByLabel("Mes").selectOption(monthName(month));
  await expect(page.getByRole("region", { name: "Totales del periodo" })).toBeVisible();
}

/** The summary of a card has no accessible name of its own, so it is opened through the text of its title. */
async function openCard(card: Locator, title: string | RegExp): Promise<void> {
  // force: with names masked the title has pointer-events none and the click goes through to the summary.
  await card.getByText(title).first().click({ force: true });
}

export function campaignCard(page: Page, name: string): Locator {
  return page.getByRole("group", { name: `Campaña ${name}`, exact: true });
}

/** Opens every campaign and line card of the margin, so that their flights can be read. */
export async function openAllCards(page: Page, margin: MarginResponse): Promise<void> {
  for (const campaign of margin.campaigns) {
    const card = campaignCard(page, campaign.name);
    await openCard(card, campaign.name);
    for (const line of campaign.lines) {
      const lineCard = card.getByRole("group", { name: `Línea ${line.line_number} de ${campaign.name}`, exact: true });
      await openCard(lineCard, new RegExp(`^Línea ${line.line_number} ·`));
    }
  }
}

/** The cell of a flight row under a column header, found by the header's position. */
export async function flightCell(table: Locator, rowIndex: number, header: string): Promise<Locator> {
  const headers = await table.getByRole("columnheader").allInnerTexts();
  const column = headers.map((text) => text.trim()).indexOf(header);
  expect(column, `the column ${header}`).toBeGreaterThanOrEqual(0);
  return table.getByRole("row").nth(rowIndex + 1).getByRole("cell").nth(column);
}

export function flightsTable(page: Page, campaign: CampaignMargin, line: LineMargin): Locator {
  return page.getByRole("table", { name: `Flights de la línea ${line.line_number} de ${campaign.name}`, exact: true });
}

/** Every flight of the margin shows on screen the state the API gives it. Cards must be open. */
export async function expectStates(page: Page, margin: MarginResponse): Promise<void> {
  for (const campaign of margin.campaigns) {
    for (const line of campaign.lines) {
      const table = flightsTable(page, campaign, line);
      for (const [index, flight] of line.flights.entries()) {
        await expect(await flightCell(table, index, "Estado")).toContainText(STATE_LABEL[flight.state]);
      }
    }
  }
}
