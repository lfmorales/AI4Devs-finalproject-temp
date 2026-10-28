import { registerCampaign } from "../support/campaigns";
import { expect, test } from "../support/fixtures";
import {
  amountsByFlight, campaignCard, chooseMonth, closedFlightsMessage, currentMonth, expectStates, flightCell, flightsOf,
  flightsTable, FRESH_DATABASE_SKIP_REASON, hasPendingClose, integer, isoDate, lastDayOf, madridToday, money, monthName,
  monthOfYear, NOTHING_TO_CLOSE, openAllCards, percent, previousMonth, readMargin, REMOVE_CAMPAIGN_FILTER,
  type MarginResponse, type Month,
} from "../support/margin";

// The closings are irreversible and the specs share one database. They rely on the order of this file (one worker,
// no parallelism): the reads and the button first, then the access check and the closing order (which clean up
// after themselves), and the real closing and its idempotency last.

const previous = previousMonth();
const current = currentMonth();
const isFirstOfMonth = madridToday().day === 1;

let closedAndKept: { before: MarginResponse; closedFlights: number } | null = null;

test.describe("the margin of the previous month, pending close", () => {
  test("shows the state, the contracted sale and the accrued revenue of every campaign as the API gives them", async ({ financeSession: page, api }) => {
    const margin = await readMargin(api, previous);
    test.skip(!hasPendingClose(margin), FRESH_DATABASE_SKIP_REASON);

    await page.goto("/margin");
    await chooseMonth(page, previous);
    await openAllCards(page, margin);

    await expectStates(page, margin);
    expect(flightsOf(margin).some((flight) => flight.state === "pending_close")).toBe(true);
    for (const campaign of margin.campaigns) {
      const summary = campaignCard(page, campaign.name).locator(":scope > summary");
      await expect(summary).toContainText(`Venta contratada ${money(campaign.totals.contracted_revenue)}`);
      await expect(summary).toContainText(`Devengado ${money(campaign.totals.revenue)}`);
      for (const line of campaign.lines) {
        const table = flightsTable(page, campaign, line);
        for (const [index, flight] of line.flights.entries()) {
          await expect(await flightCell(table, index, "Venta contratada")).toHaveText(money(flight.contracted_revenue));
          await expect(await flightCell(table, index, "Devengado")).toHaveText(money(flight.revenue));
        }
      }
    }
  });
});

test.describe("the margin of the current month, running", () => {
  test.skip(isFirstOfMonth, "Today (Madrid) is the first of the month: no flight of this month has started yet.");

  test("shows the state, the days and the delivery of every running flight as the API gives them", async ({ financeSession: page, api }) => {
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
          await expect(await flightCell(table, index, "Entrega")).toHaveText(
            `Entregado ${integer(flight.delivered_impressions)} de ${integer(flight.contracted_impressions)} impresiones`,
          );
        }
      }
    }
  });

  test("labels a negative margin and a flight without a sale exactly where the API raises them", async ({ financeSession: page, api }) => {
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
    // The API gives a null percentage only for the flights without a sale, and the screen shows a dash there.
    expect(flights.filter((flight) => flight.margin_pct === null).every((flight) => flight.zero_sale)).toBe(true);
  });
});

test.describe("the close-month button", () => {
  test("is off with a campaign filter, with the reason", async ({ financeSession: page, api }) => {
    const margin = await readMargin(api, previous);
    const campaign = margin.campaigns[0];
    test.skip(campaign === undefined, FRESH_DATABASE_SKIP_REASON);

    await page.goto("/margin");
    await chooseMonth(page, previous);
    await page.getByLabel("Campaña").selectOption(String(campaign?.campaign_id));

    const button = page.getByRole("button", { name: "Cerrar mes" });
    await expect(button).toBeDisabled();
    await expect(button).toHaveAccessibleDescription(REMOVE_CAMPAIGN_FILTER);
  });

  test("is off in a month with only running flights, with the reason", async ({ financeSession: page, api }) => {
    const margin = await readMargin(api, current);
    test.skip(hasPendingClose(margin), FRESH_DATABASE_SKIP_REASON);

    await page.goto("/margin");
    await chooseMonth(page, current);

    const button = page.getByRole("button", { name: "Cerrar mes" });
    await expect(button).toBeDisabled();
    await expect(button).toHaveAccessibleDescription(NOTHING_TO_CLOSE);
  });

  test("is on in a month with a flight pending close", async ({ financeSession: page, api }) => {
    test.skip(!hasPendingClose(await readMargin(api, previous)), FRESH_DATABASE_SKIP_REASON);

    await page.goto("/margin");
    await chooseMonth(page, previous);

    await expect(page.getByRole("button", { name: "Cerrar mes" })).toBeEnabled();
  });
});

test.describe("the access to the closing", () => {
  test("shows 'Acceso denegado' when the closing answers 403", async ({ financeSession: page, api }) => {
    test.skip(!hasPendingClose(await readMargin(api, previous)), FRESH_DATABASE_SKIP_REASON);
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
  test("names the earlier month that blocks the closing, and leaves the database able to close", async ({ financeSession: page, api }) => {
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

      await page.goto("/margin");
      await chooseMonth(page, previous);
      await page.getByRole("button", { name: "Cerrar mes" }).click();
      await page.getByRole("dialog").getByRole("button", { name: "Confirmar cierre" }).click();

      await expect(page.getByRole("alert")).toHaveText(
        `Hay un mes anterior sin cerrar: ${monthOfYear(earlier)}. Ciérralo antes de cerrar ${monthOfYear(previous)}.`,
      );
      expect(hasPendingClose(await readMargin(api, previous)), "nothing was closed").toBe(true);
    } finally {
      if (registered) {
        const cleanup = await api.post("margin/closings", { data: earlier });
        expect(cleanup.ok(), `closing ${monthName(earlier.month)} again to leave the database able to close`).toBe(true);
      }
    }
  });
});

test.describe("the real closing", () => {
  test.skip(isFirstOfMonth, "Today (Madrid) is the first of the month: the closing depends on flights that ended yesterday.");

  test("freezes the rates, closes what the API counts and changes no amount", async ({ financeSession: page, api }) => {
    const before = await readMargin(api, previous);
    test.skip(!hasPendingClose(before), FRESH_DATABASE_SKIP_REASON);
    const closing = flightsOf(before).filter((flight) => flight.state === "pending_close").length;

    await page.goto("/margin");
    await chooseMonth(page, previous);
    await page.getByRole("button", { name: "Cerrar mes" }).click();
    const dialog = page.getByRole("dialog", { name: `Cerrar ${monthOfYear(previous)}` });
    await expect(dialog).toContainText("congela las tasas");
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

  test("is idempotent: the button is off and a second closing changes nothing", async ({ financeSession: page, api }) => {
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
