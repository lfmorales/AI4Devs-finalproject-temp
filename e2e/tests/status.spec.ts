import { expect, test } from "../support/fixtures";
import { madridDayOfMonth, RUNNING_FLIGHT_SKIP_REASON } from "../support/format";

interface StatusRow {
  campaign: { id: number; name: string };
  missing_data_flag: boolean;
  pacing_flag: boolean;
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

  test("shows the text of every flag the API raises", async ({ financeSession: page, api }) => {
    test.skip(madridDayOfMonth() === 1, RUNNING_FLIGHT_SKIP_REASON);
    const rows = (await (await api.get("campaign-status")).json()) as StatusRow[];
    const flagged = rows.map((row, index) => ({ row, index })).filter(({ row }) => row.missing_data_flag || row.pacing_flag);
    test.skip(flagged.length === 0, "No row of the seeded data carries a flag, so there is no flag text to read.");

    await page.goto("/status");

    const bodyRows = page.getByRole("table", { name: "Estado de las campañas" }).getByRole("row");
    for (const { row, index } of flagged) {
      const flags = bodyRows.nth(index + 1).getByRole("listitem");
      if (row.missing_data_flag) await expect(flags.filter({ hasText: "Sin datos recibidos" })).toHaveCount(1);
      if (row.pacing_flag) await expect(flags.filter({ hasText: "Desviación de ritmo" })).toHaveCount(1);
    }
  });
});
