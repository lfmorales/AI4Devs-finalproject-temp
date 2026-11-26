import { appAlert } from "../support/alerts";
import { registerCampaign } from "../support/campaigns";
import { expect, test } from "../support/fixtures";
import {
  amountsByFlight, campaignCard, campaignField, chooseMonth, closedFlightsMessage, currentMonth, deliveryLegend, expectStates, flightCell, flightsOf,
  flightsTable, FRESH_DATABASE_SKIP_REASON, hasPendingClose, isoDate, lastDayOf, madridToday, money, monthName,
  monthOfYear, NOTHING_TO_CLOSE, openAllCards, PENDING_REVIEW, percent, previousMonth, readMargin, REMOVE_CAMPAIGN_FILTER, reviewMonth,
  saleLabel,
  type CampaignMargin, type LineMargin, type MarginResponse, type Month,
} from "../support/margin";

// The closings are irreversible and the specs share one database. They rely on the order of this file (one worker,
// no parallelism): the reads and the button first, then the access check and the closing order (which clean up
// after themselves), and the real closing and its idempotency last.

const previous = previousMonth();
const current = currentMonth();
const isFirstOfMonth = madridToday().day === 1;
// The Deal demo of seed_margin_demo: a target line on Equativ whose previous month is the worked example.
const DEAL_DEMO = "DEMO-MARGEN-DEAL";

let closedAndKept: { before: MarginResponse; closedFlights: number } | null = null;

test.describe("the margin of the previous month, pending close", () => {
  test("shows the state, the contracted sale and the accrued revenue of every campaign as the API gives them", async ({ operationsSession: page, api }) => {
    const margin = await readMargin(api, previous);
    test.skip(!hasPendingClose(margin), FRESH_DATABASE_SKIP_REASON);

    await page.goto("/margin");
    await chooseMonth(page, previous);
    await openAllCards(page, margin);

    await expectStates(page, margin);
    expect(flightsOf(margin).some((flight) => flight.state === "pending_close")).toBe(true);
    for (const campaign of margin.campaigns) {
      const summary = campaignCard(page, campaign.name).locator(":scope > summary");
      // A target campaign (the Deal demo) names its sale «Venta objetivo».
      await expect(summary).toContainText(`${saleLabel(campaign.totals.volume_commitment)} ${money(campaign.totals.contracted_revenue)}`);
      // Every flight of the previous month has ended: its billing is «Facturable», not «Facturable a la fecha».
      await expect(summary).toContainText(`Facturable ${money(campaign.totals.revenue)}`);
      for (const line of campaign.lines) {
        const table = flightsTable(page, campaign, line);
        for (const [index, flight] of line.flights.entries()) {
          await expect(await flightCell(table, index, saleLabel(flight.volume_commitment))).toHaveText(money(flight.contracted_revenue));
          await expect(await flightCell(table, index, "Facturable")).toHaveText(money(flight.revenue));
        }
      }
    }
  });
});

test.describe("the Deal demo of the previous month", () => {
  test("its flight is the worked example: «Venta objetivo», «Bruto» and the margin of GET /api/margin", async ({ operationsSession: page, api }) => {
    const margin = await readMargin(api, previous);
    const deal = margin.campaigns.find((campaign) => campaign.name === DEAL_DEMO);
    expect(deal, `${DEAL_DEMO} in GET /api/margin: run reset-data.sh`).toBeDefined();
    const campaign = deal as CampaignMargin;
    const [line] = campaign.lines;
    const [flight] = line?.flights ?? [];
    // The worked example of the change: a target of 1,000,000 at 5.00 €, 1,100,000 served, 4,400.00 € reported.
    expect([flight?.volume_commitment, flight?.contracted_revenue, flight?.revenue, flight?.gross_revenue, flight?.margin]).toEqual(
      ["target", "5000.00", "4400.00", "5500.00", "2750.00"],
    );

    await page.goto("/margin");
    await chooseMonth(page, previous);
    await openAllCards(page, { campaigns: [campaign] });

    const summary = campaignCard(page, DEAL_DEMO).locator(":scope > summary");
    await expect(summary).toContainText(`Venta objetivo ${money(campaign.totals.contracted_revenue)}`);
    await expect(summary).toContainText(`Bruto ${money(campaign.totals.gross_revenue ?? "")}`);
    const table = flightsTable(page, campaign, line as LineMargin);
    await expect(await flightCell(table, 0, "Venta objetivo")).toHaveText(money("5000.00"));
    await expect(await flightCell(table, 0, "Facturable")).toHaveText(money("4400.00"));
    await expect(await flightCell(table, 0, "Bruto")).toHaveText(money("5500.00"));
    await expect(await flightCell(table, 0, "Margen")).toHaveText(money("2750.00"));
    await expect(await flightCell(table, 0, "% de margen")).toHaveText(percent("62.50"));
  });
});

test.describe("the margin of the current month, running", () => {
  test.skip(isFirstOfMonth, "Today (Madrid) is the first of the month: no flight of this month has started yet.");

  test("shows the state, the days and the delivery of every running flight as the API gives them", async ({ operationsSession: page, api }) => {
    const margin = await readMargin(api, current);
    const running = flightsOf(margin).filter((flight) => flight.state === "running");
    test.skip(running.length === 0, FRESH_DATABASE_SKIP_REASON);

    await page.goto("/margin");
    await chooseMonth(page, current);
    await openAllCards(page, margin);

    await expectStates(page, margin);
    for (const campaign of margin.campaigns) {
      for (const line of campaign.lines) {
        const table = flightsTable(page, campaign, line);
        for (const [index, flight] of line.flights.entries()) {
          if (flight.state === "running") {
            await expect(await flightCell(table, index, "Estado")).toContainText(`${flight.accrued_days} de ${flight.window_days} días`);
          }
          await expect(await flightCell(table, index, "Entrega")).toHaveText(deliveryLegend(flight));
        }
      }
    }
  });

  test("says OTS on the DOOH demo flights and impresiones on those of the DEMO Channel", async ({ operationsSession: page, api }) => {
    const margin = await readMargin(api, current);
    const dooh = margin.campaigns.find((campaign) => campaign.name === "DEMO-MARGEN-DOOH");
    const impressions = margin.campaigns.find((campaign) => campaign.name === "DEMO-MARGEN-CURSO");
    expect(dooh, "the DOOH demo campaign is in GET /api/margin: run reset-data.sh").toBeDefined();
    expect(impressions, "the DEMO Channel demo campaign is in GET /api/margin").toBeDefined();
    if (dooh === undefined || impressions === undefined) return;

    await page.goto("/margin");
    await chooseMonth(page, current);
    await openAllCards(page, margin);

    for (const [campaign, metric] of [[dooh, "ots"], [impressions, "impressions"]] as const) {
      for (const line of campaign.lines) {
        const table = flightsTable(page, campaign, line);
        for (const [index, flight] of line.flights.entries()) {
          expect(flight.delivery_metric).toBe(metric);
          const legend = await flightCell(table, index, "Entrega");
          await expect(legend).toHaveText(deliveryLegend(flight));
          await expect(legend).toContainText(metric === "ots" ? /de [\d.]+ OTS$/ : /de [\d.]+ impresiones$/);
        }
      }
    }
  });

  test("labels a negative margin and a flight without a sale exactly where the API raises them", async ({ operationsSession: page, api }) => {
    const margin = await readMargin(api, current);
    const flights = flightsOf(margin);
    test.skip(!flights.some((flight) => flight.below_cost) || !flights.some((flight) => flight.zero_sale), FRESH_DATABASE_SKIP_REASON);

    await page.goto("/margin");
    await chooseMonth(page, current);
    await openAllCards(page, margin);

    for (const campaign of margin.campaigns) {
      for (const line of campaign.lines) {
        const table = flightsTable(page, campaign, line);
        for (const [index, flight] of line.flights.entries()) {
          const warnings = await flightCell(table, index, "Avisos");
          if (flight.below_cost) await expect(warnings).toContainText("Margen negativo");
          else await expect(warnings).not.toContainText("Margen negativo");
          if (flight.zero_sale) await expect(warnings).toContainText("Sin venta");
          else await expect(warnings).not.toContainText("Sin venta");
          await expect(await flightCell(table, index, "% de margen")).toHaveText(percent(flight.margin_pct));
        }
      }
    }
    // The API gives a null percentage only for the flights with no revenue, and the screen shows a dash there: a flight
    // without a sale, or a committed flight that has billed nothing yet, since a committed flight earns its billing, the
    // lesser of delivered and contracted (committed-billing-and-review). The running demo flights with no delivery, such
    // as the exceptions demo's, are of the second kind.
    expect(flights.filter((flight) => flight.margin_pct === null).every((flight) => flight.revenue === "0.00")).toBe(true);
    expect(flights.filter((flight) => flight.zero_sale).every((flight) => flight.margin_pct === null)).toBe(true);
  });
});

test.describe("the close-month button", () => {
  test("is off with a campaign filter, with the reason", async ({ operationsSession: page, api }) => {
    const margin = await readMargin(api, previous);
    const campaign = margin.campaigns[0];
    test.skip(campaign === undefined, FRESH_DATABASE_SKIP_REASON);

    await page.goto("/margin");
    await chooseMonth(page, previous);
    await campaignField(page).selectOption(String(campaign?.campaign_id));

    const button = page.getByRole("button", { name: "Cerrar mes" });
    await expect(button).toBeDisabled();
    await expect(button).toHaveAccessibleDescription(REMOVE_CAMPAIGN_FILTER);
  });

  test("is off in a month with only running flights, with the reason", async ({ operationsSession: page, api }) => {
    const margin = await readMargin(api, current);
    test.skip(hasPendingClose(margin), FRESH_DATABASE_SKIP_REASON);

    await page.goto("/margin");
    await chooseMonth(page, current);

    const button = page.getByRole("button", { name: "Cerrar mes" });
    await expect(button).toBeDisabled();
    await expect(button).toHaveAccessibleDescription(NOTHING_TO_CLOSE);
  });

  test("is off while a campaign of the month is pending review, with the reason", async ({ operationsSession: page, api }) => {
    test.skip(!hasPendingClose(await readMargin(api, previous)), FRESH_DATABASE_SKIP_REASON);
    const billing = await api.get(`billing?year=${previous.year}&month=${previous.month}`);
    const states = ((await billing.json()) as { campaigns: { review_state: string }[] }).campaigns.map((c) => c.review_state);
    test.skip(!states.includes("pending_review"), "Las campañas del mes previo ya están revisadas: ejecuta reset-data.sh.");

    await page.goto("/margin");
    await chooseMonth(page, previous);

    const button = page.getByRole("button", { name: "Cerrar mes" });
    await expect(button).toHaveAccessibleDescription(PENDING_REVIEW);
    await expect(button).toBeDisabled();
  });

  test("is on in a month with a flight pending close once every campaign of it is reviewed", async ({ operationsSession: page, api }) => {
    test.skip(!hasPendingClose(await readMargin(api, previous)), FRESH_DATABASE_SKIP_REASON);
    await reviewMonth(api, previous);

    await page.goto("/margin");
    await chooseMonth(page, previous);

    await expect(page.getByRole("button", { name: "Cerrar mes" })).toBeEnabled();
  });
});

test.describe("the access to the closing", () => {
  test("shows 'Acceso denegado' when the closing answers 403", async ({ operationsSession: page, api }) => {
    test.skip(!hasPendingClose(await readMargin(api, previous)), FRESH_DATABASE_SKIP_REASON);
    await reviewMonth(api, previous); // the button is on only once the month is reviewed
    await page.route(/\/api\/margin\/closings$/, (route) =>
      route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ code: "forbidden", message: "simulated" }) }),
    );

    await page.goto("/margin");
    await chooseMonth(page, previous);
    await page.getByRole("button", { name: "Cerrar mes" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Confirmar cierre" }).click();

    await expect(page.getByRole("heading", { name: "Acceso denegado" })).toBeVisible();
    await expect(page.getByText("No tienes permiso para ver el margen.")).toBeVisible();
  });
});

test.describe("the closing order", () => {
  test("names the earlier month that blocks the closing, and leaves the database able to close", async ({ operationsSession: page, api }) => {
    const earlier: Month = { year: previous.year, month: previous.month - 3 };
    test.skip(earlier.month < 1, "No hay un mes anterior en el mismo año: el mes previo es de enero a marzo.");
    const all = await readMargin(api);
    const staleBefore = flightsOf(all).filter(
      (flight) => flight.state === "pending_close" && (flight.period_year < previous.year || (flight.period_year === previous.year && flight.period_month < previous.month)),
    );
    test.skip(staleBefore.length > 0, "Ya hay flights pendientes de cierre en un mes anterior al previo: ejecuta reset-data.sh en lugar de apilar más.");
    test.skip(!hasPendingClose(await readMargin(api, previous)), FRESH_DATABASE_SKIP_REASON);

    const name = `E2E-ORDEN-${Date.now()}`;
    let registered = false;
    try {
      await registerCampaign(api, {
        name,
        start: isoDate(earlier.year, earlier.month, 1),
        end: isoDate(earlier.year, earlier.month, lastDayOf(earlier)),
        orderReceivedOn: isoDate(earlier.year, earlier.month, 1),
      });
      registered = true;
      await reviewMonth(api, previous); // the button is on only once the month is reviewed

      await page.goto("/margin");
      await chooseMonth(page, previous);
      await page.getByRole("button", { name: "Cerrar mes" }).click();
      await page.getByRole("dialog").getByRole("button", { name: "Confirmar cierre" }).click();

      await expect(appAlert(page)).toHaveText(
        `Hay un mes anterior sin cerrar: ${monthOfYear(earlier)}. Ciérralo antes de cerrar ${monthOfYear(previous)}.`,
      );
      expect(hasPendingClose(await readMargin(api, previous)), "nothing was closed").toBe(true);
    } finally {
      if (registered) {
        await reviewMonth(api, earlier);
        const cleanup = await api.post("margin/closings", { data: earlier });
        expect(cleanup.ok(), `closing ${monthName(earlier.month)} again to leave the database able to close`).toBe(true);
      }
    }
  });
});

test.describe("the real closing", () => {
  test.skip(isFirstOfMonth, "Today (Madrid) is the first of the month: the closing depends on flights that ended yesterday.");

  test("freezes the rates, closes what the API counts and changes no amount", async ({ operationsSession: page, api }) => {
    const before = await readMargin(api, previous);
    test.skip(!hasPendingClose(before), FRESH_DATABASE_SKIP_REASON);
    const closing = flightsOf(before).filter((flight) => flight.state === "pending_close").length;
    await reviewMonth(api, previous);

    await page.goto("/margin");
    await chooseMonth(page, previous);
    await page.getByRole("button", { name: "Cerrar mes" }).click();
    const dialog = page.getByRole("dialog", { name: `Cerrar ${monthOfYear(previous)}` });
    await expect(dialog).toContainText("congela todas las cifras de cada flight terminado y la entrega con que se calcularon");
    await expect(dialog).toContainText("solo activa el aviso «Cambió tras el cierre»");
    await expect(dialog).toContainText("no se puede deshacer");
    await expect(dialog).toContainText("de todas las campañas del mes");
    await dialog.getByRole("button", { name: "Confirmar cierre" }).click();

    await expect(page.getByText(closedFlightsMessage(closing, previous))).toBeVisible();
    const after = await readMargin(api, previous);
    expect(flightsOf(after).every((flight) => flight.state === "closed"), "every flight is closed in the API").toBe(true);
    await openAllCards(page, after);
    await expectStates(page, after);
    expect(amountsByFlight(after)).toEqual(amountsByFlight(before));
    closedAndKept = { before, closedFlights: flightsOf(after).length };
  });

  test("is idempotent: the button is off and a second closing changes nothing", async ({ operationsSession: page, api }) => {
    test.skip(closedAndKept === null, "El cierre real no se ha ejecutado en esta pasada, así que no hay nada que repetir.");
    const kept = closedAndKept as NonNullable<typeof closedAndKept>;
    const before = await readMargin(api, previous);

    await page.goto("/margin");
    await chooseMonth(page, previous);
    const button = page.getByRole("button", { name: "Cerrar mes" });
    await expect(button).toBeDisabled();
    await expect(button).toHaveAccessibleDescription(NOTHING_TO_CLOSE);

    const again = await api.post("margin/closings", { data: previous });
    expect(again.ok()).toBe(true);
    expect(((await again.json()) as { closed: number }).closed).toBe(0);
    const after = await readMargin(api, previous);
    expect(flightsOf(after).filter((flight) => flight.state === "closed")).toHaveLength(kept.closedFlights);
    expect(amountsByFlight(after)).toEqual(amountsByFlight(before));
    expect(amountsByFlight(after)).toEqual(amountsByFlight(kept.before));
  });
});
