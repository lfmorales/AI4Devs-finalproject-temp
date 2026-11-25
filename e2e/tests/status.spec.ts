import { registerCampaign } from "../support/campaigns";
import { expect, test } from "../support/fixtures";
import { formatDecimalEsEs, formatQuantityEsEs, unitLabel } from "../support/format";

interface StatusRow {
  campaign: { id: number; name: string };
  contracted_impressions: number;
  delivery_metric: "impressions" | "ots";
  delivered: string;
  missing_data_flag: boolean;
  pacing_flag: boolean;
  volume_commitment: "committed" | "target";
  pacing: { deviation: number | null; status: "on_pace" | "under_delivering" | "over_delivering" };
}

// The Deal demo of seed_margin_demo: a target line on Equativ that delivers above its target.
const DEAL_DEMO = "DEMO-MARGEN-DEAL";

/** Today in Madrid as YYYY-MM-DD, shifted by whole days. */
function madridDate(offsetDays: number): string {
  const day = new Date(Date.now() + offsetDays * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Madrid" }).format(day);
}

test.describe("the campaign status", () => {
  test("lists the rows of GET /api/campaign-status, in number and in campaign", async ({ operationsSession: page, api }) => {
    const rows = (await (await api.get("campaign-status")).json()) as StatusRow[];

    await page.goto("/status");

    if (rows.length === 0) {
      await expect(page.getByText("No hay campañas en curso")).toBeVisible();
      return;
    }
    const table = page.getByRole("table", { name: "Estado de las campañas" });
    // The header row is the first one.
    await expect(table.getByRole("row")).toHaveCount(rows.length + 1);
    const bodyRows = table.getByRole("row");
    for (const [index, row] of rows.entries()) {
      await expect(bodyRows.nth(index + 1).getByRole("cell").first()).toHaveText(row.campaign.name);
    }
  });

  test("says OTS on the DOOH demo row with the volume of the API, and impresiones on the DEMO Channel ones", async ({ operationsSession: page, api }) => {
    const rows = (await (await api.get("campaign-status")).json()) as StatusRow[];
    const dooh = rows.filter((row) => row.delivery_metric === "ots");
    // The DEMO Channel rows are committed; the Deal demo, a target, labels its volume «Objetivo» and is checked below.
    const impressions = rows.filter(
      (row) => row.delivery_metric === "impressions" && row.campaign.name.startsWith("DEMO-MARGEN-") && row.volume_commitment === "committed",
    );
    expect(dooh.map((row) => row.campaign.name), "the DOOH demo row is in GET /api/campaign-status: run reset-data.sh").toContain("DEMO-MARGEN-DOOH");
    expect(impressions.length, "the DEMO Channel demo rows").toBeGreaterThan(0);

    await page.goto("/status");

    const table = page.getByRole("table", { name: "Estado de las campañas" });
    // The headers are read at once by allInnerTexts: wait until the table has been drawn.
    await expect(table.getByRole("columnheader", { name: "Unidad" })).toBeVisible();
    const headers = (await table.getByRole("columnheader").allInnerTexts()).map((text) => text.trim());
    const cell = (row: StatusRow, header: string) =>
      table.getByRole("row").filter({ hasText: row.campaign.name }).getByRole("cell").nth(headers.indexOf(header));
    for (const row of [...dooh, ...impressions]) {
      await expect(cell(row, "Unidad")).toHaveText(unitLabel(row.delivery_metric));
      await expect(cell(row, "Contratado")).toHaveText(formatDecimalEsEs(String(row.contracted_impressions)));
      await expect(cell(row, "Entregado")).toHaveText(formatQuantityEsEs(row.delivered));
    }
    // The DOOH row carries OTS with decimals, which the screen shows as received.
    const doohRow = dooh.find((row) => row.campaign.name === "DEMO-MARGEN-DOOH");
    expect(doohRow?.delivered).toMatch(/\.\d{4}$/);
  });

  test("shows the two flags of a campaign whose running flight has received no delivery", async ({ operationsSession: page, api }) => {
    // The line starts five days ago and ends in five days, so a flight contains D-1 whatever the day of the month is.
    const start = madridDate(-5);
    const end = madridDate(5);
    const name = `E2E-SIN-ENTREGA-${Date.now()}`;

    await registerCampaign(api, { name, start, end, orderReceivedOn: madridDate(-6) });

    const rows = (await (await api.get("campaign-status")).json()) as StatusRow[];
    const row = rows.find((candidate) => candidate.campaign.name === name);
    expect(row, "the new campaign is in GET /api/campaign-status").toBeDefined();
    expect(row?.missing_data_flag).toBe(true);
    expect(row?.pacing_flag).toBe(true);

    await page.goto("/status");

    const flags = page.getByRole("table", { name: "Estado de las campañas" }).getByRole("row").filter({ hasText: name }).getByRole("listitem");
    await expect(flags).toHaveText(["Sin datos recibidos", "Desviación de ritmo"]);
  });
});


test.describe("a target line in the campaign status", () => {
  test("the Deal demo's row says «Objetivo» and shows no pacing tag, although it is above its target", async ({ operationsSession: page, api }) => {
    const rows = (await (await api.get("campaign-status")).json()) as StatusRow[];
    const deal = rows.find((row) => row.campaign.name === DEAL_DEMO);
    expect(deal, `${DEAL_DEMO} in GET /api/campaign-status: run reset-data.sh`).toBeDefined();
    const row = deal as StatusRow;
    expect([row.volume_commitment, row.pacing_flag]).toEqual(["target", false]);
    expect(row.pacing.deviation ?? 0, "the Deal demo delivers above its target").toBeGreaterThan(0);

    await page.goto("/status");

    const shown = page.getByRole("table", { name: "Estado de las campañas" }).getByRole("row").filter({ hasText: DEAL_DEMO });
    await expect(shown).toHaveCount(1);
    await expect(shown).toContainText(`Objetivo ${formatDecimalEsEs(String(row.contracted_impressions))}`);
    await expect(shown).not.toContainText("Desviación de ritmo");
  });
});
