import { expect, test } from "../support/fixtures";

interface StatusRow {
  campaign: { id: number; name: string };
  missing_data_flag: boolean;
  pacing_flag: boolean;
}

interface MasterItem {
  id: number;
  name: string;
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
    const firstOf = async (path: string): Promise<number> => {
      const items = (await (await api.get(path)).json()) as MasterItem[];
      const first = items[0];
      if (first === undefined) throw new Error(`GET /api/${path} has no item: the masters are not loaded.`);
      return first.id;
    };
    // The line starts five days ago and ends in five days, so a flight contains D-1 whatever the day of the month is.
    const start = madridDate(-5);
    const end = madridDate(5);
    const name = `E2E-SIN-ENTREGA-${Date.now()}`;

    // The body follows CampaignCreateRequest and CampaignLineCreateRequest of the backend's OpenAPI schema.
    const registration = await api.post("campaigns", {
      data: {
        name,
        display_name: name,
        agency_id: await firstOf("masters/agencies"),
        advertiser_id: await firstOf("masters/advertisers"),
        campaign_type_id: await firstOf("masters/campaign-types"),
        sector_id: await firstOf("masters/sectors"),
        sales_rep_id: await firstOf("masters/sales-reps"),
        start_date: start,
        end_date: end,
        order_reference: name,
        order_received_on: madridDate(-6),
        lines: [
          {
            start_date: start,
            end_date: end,
            dsp_id: await firstOf("masters/dsps"),
            channel_id: await firstOf("masters/channels"),
            format_id: await firstOf("masters/formats"),
            scope: "national",
            market_description: "E2E",
            contracted_impressions: 1_000_000,
            sale_cpm: "1.00",
          },
        ],
      },
    });
    expect(registration.status(), "the registration of the campaign").toBe(201);

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
