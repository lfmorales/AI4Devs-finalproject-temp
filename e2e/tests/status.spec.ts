import { registerCampaign } from "../support/campaigns";
import { expect, test } from "../support/fixtures";

interface StatusRow {
  campaign: { id: number; name: string };
  missing_data_flag: boolean;
  pacing_flag: boolean;
}

/** Today in Madrid as YYYY-MM-DD, shifted by whole days. */
function madridDate(offsetDays: number): string {
  const day = new Date(Date.now() + offsetDays * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Madrid" }).format(day);
}

test.describe("the campaign status", () => {
  test("lists the rows of GET /api/campaign-status, in number and in campaign", async ({ financeSession: page, api }) => {
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

  test("shows the two flags of a campaign whose running flight has received no delivery", async ({ financeSession: page, api }) => {
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
