import { readFileSync } from "node:fs";

import { registerCampaign } from "../support/campaigns";
import { expect, signInAs, test } from "../support/fixtures";
import {
  chooseMonth, closedFlightsMessage, flightCell, flightsOf, isoDate, lastDayOf, money, monthName, monthOfYear, previousMonth,
  readMargin, type Month,
} from "../support/margin";

/** The parts of GET /api/billing this spec reads, as the backend's OpenAPI schema publishes them. */
interface BillingFlight {
  flight_id: number;
  billing: string | null;
  billing_basis: string | null;
  adjustment: { reason: string; created_by_name: string } | null;
}
interface BillingCampaign {
  name: string;
  review_state: string;
  lines: { line_number: number; flights: BillingFlight[] }[];
}

const previous = previousMonth();
// Two months back, in the previous month's year: the DEMO DSP's load (seed_margin_demo) starts on 1 January of that
// year, and a month is reviewed only once its DSP has loaded its last day. Every demo flight starts in the previous
// month or later, so no earlier month of that year is open and the closing is not refused with previous_month_open.
const target: Month = { year: previous.year, month: previous.month - 1 };
const REASON = "Acuerdo con la agencia: se factura la OC completa";
const name = `E2E-FACTURA-${Date.now()}`;

test.describe.configure({ mode: "serial" });

test.describe("the billing of a month, from the adjustment to the CSV", () => {
  test.skip(
    target.month < 1,
    "Necesita dos meses anteriores del mismo año: el mes previo es enero, y la carga del DEMO DSP empieza el 1 de enero de su año.",
  );

  test("Finance reviews a campaign, adjusts its flight, sees it back to pending and reviews it again", async ({ page, api }) => {
    const earlierOpen = flightsOf(await readMargin(api)).filter(
      (flight) => flight.state === "pending_close" && flight.period_year === target.year && flight.period_month < target.month,
    );
    test.skip(earlierOpen.length > 0, `Hay flights pendientes de cierre antes de ${monthOfYear(target)}: ejecuta reset-data.sh.`);
    await registerCampaign(api, {
      name,
      start: isoDate(target.year, target.month, 1),
      end: isoDate(target.year, target.month, lastDayOf(target)),
      orderReceivedOn: isoDate(target.year, target.month, 1),
    });
    await signInAs(page, "finance");

    await page.goto("/billing");
    await chooseBillingMonth(page, target);
    const campaign = page.getByRole("region", { name: `Campaña ${name}`, exact: true });
    await expect(campaign).toContainText("Pendiente de revisión");
    await campaign.getByRole("button", { name: "Marcar como revisada" }).click();
    await expect(campaign).toContainText("Revisada por E2E finance el");

    const table = campaign.getByRole("table", { name: `Flights de la línea 1 de ${name}`, exact: true });
    await table.getByRole("button", { name: "Ajustar" }).click();
    const dialog = page.getByRole("dialog", { name: "Ajustar la facturación" });
    await dialog.getByLabel("Base").selectOption({ label: "Lo contratado (el tope)" });
    await dialog.getByLabel("Motivo").fill(REASON);
    await dialog.getByRole("button", { name: "Guardar ajuste" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Ajuste guardado" })).toBeVisible();

    const flight = await billingFlightOf(api, target, name);
    expect([flight.billing_basis, flight.adjustment?.reason, flight.adjustment?.created_by_name]).toEqual(["contracted", REASON, "E2E finance"]);
    await expect(await flightCell(table, 0, "Facturable")).toHaveText(money(flight.billing ?? ""));
    await expect(await flightCell(table, 0, "Ajuste")).toContainText(`Ajustado: lo contratado (el tope) · ${REASON} · E2E finance ·`);
    await expect(campaign).toContainText("Pendiente de revisión");

    await campaign.getByRole("button", { name: "Marcar como revisada" }).click();
    await expect(campaign).toContainText("Revisada por E2E finance el");
  });

  test("Operations closes the month and downloads its CSV, with the adjusted amount and the reason", async ({ operationsSession: page, api }) => {
    const billing = await billingFlightOf(api, target, name);

    await page.goto("/margin");
    await chooseMonth(page, target);
    await page.getByRole("button", { name: "Cerrar mes" }).click();
    await page.getByRole("dialog", { name: `Cerrar ${monthOfYear(target)}` }).getByRole("button", { name: "Confirmar cierre" }).click();
    await expect(page.getByText(closedFlightsMessage(1, target))).toBeVisible();

    await page.goto("/billing");
    await chooseBillingMonth(page, target);
    await expect(page.getByRole("region", { name: `Campaña ${name}`, exact: true })).toContainText("Cerrada");
    const downloading = page.waitForEvent("download");
    await page.getByRole("button", { name: "Descargar CSV" }).click();
    const download = await downloading;

    const mm = String(target.month).padStart(2, "0");
    expect(download.suggestedFilename()).toBe(`facturacion-${target.year}-${mm}.csv`);
    const saved = readFileSync(await download.path());
    const exported = await api.get(`billing/export?year=${target.year}&month=${target.month}`);
    expect(exported.status()).toBe(200);
    expect(saved.equals(Buffer.from(await exported.body())), "the file saved is GET /api/billing/export").toBe(true);
    expect([...saved.subarray(0, 3)]).toEqual([0xef, 0xbb, 0xbf]);
    const rows = saved.subarray(3).toString("utf8").split("\r\n").filter((row) => row !== "").map((row) => row.split(";"));
    expect(rows[0]).toEqual(["cliente", "agencia", "campaña", "línea", "orden de compra", "entregado", "contratado", "arrastre", "facturable", "CPM", "importe", "ajustado", "motivo"]);
    const row = rows.find((fields) => fields[2] === name);
    expect(row, `the row of ${name}`).toBeDefined();
    // importe, ajustado and motivo: the billing frozen with the adjustment, written with a decimal comma.
    expect(row?.slice(10)).toEqual([(billing.billing ?? "").replace(".", ","), "sí", REASON]);
  });
});

async function chooseBillingMonth(page: import("@playwright/test").Page, month: Month): Promise<void> {
  await page.getByRole("textbox", { name: "Año", exact: true }).fill(String(month.year));
  await page.getByRole("combobox", { name: "Mes", exact: true }).selectOption(monthName(month.month));
  await expect(page.getByRole("status").filter({ hasText: "Cargando facturación…" })).toHaveCount(0);
}

async function billingFlightOf(api: import("@playwright/test").APIRequestContext, month: Month, campaign: string): Promise<BillingFlight> {
  const response = await api.get(`billing?year=${month.year}&month=${month.month}`);
  expect(response.ok(), "GET /api/billing").toBe(true);
  const found = ((await response.json()) as { campaigns: BillingCampaign[] }).campaigns.find((item) => item.name === campaign);
  const flight = found?.lines[0]?.flights[0];
  expect(flight, `${campaign} in GET /api/billing`).toBeDefined();
  return flight as BillingFlight;
}
