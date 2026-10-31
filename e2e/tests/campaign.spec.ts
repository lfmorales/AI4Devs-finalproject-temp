import { appAlert } from "../support/alerts";
import {
  addMonths, calculateButton, countRegistrations, fillCampaign, firstDayOf, lastDateOf, monthLabel, openNewCampaign,
  readMasterChoices, shownVolumes, submitButton, uniqueCampaignName, volumeFields, waitForRegistration,
  type RegisteredCampaign,
} from "../support/campaign-form";
import { expect, test } from "../support/fixtures";
import {
  campaignCard, chooseMonth, currentMonth, flightCell, flightsOf, flightsTable, isoDate, openAllCards, percent, previousMonth,
  readMargin,
} from "../support/margin";

// The registration is a Spanish form over the real backend. Nothing here is deleted afterwards: every campaign has a
// unique E2E-ALTA-<timestamp> name and reset-data.sh removes them. The stored flights cannot be read back on their
// own (there is no GET /api/campaigns/{id}), so the registration's own response stands for them.

const TOTAL = 3_000_007; // not divisible by three, so the proportional split has a remainder to place
const MESSAGES = {
  mismatch: "Los volúmenes mensuales deben sumar el total de la línea.",
  fix: "Por favor corrige los errores antes de enviar.",
  negativeCpm: "El CPM (venta) no puede ser negativo",
  startOutside: "La fecha de inicio de la línea debe estar dentro de las fechas de la campaña.",
  tooSmall: "El volumen de la línea es demasiado pequeño para dar impresiones a todos los meses.",
  genericPreview: "No se pudo calcular el reparto. Inténtalo de nuevo.",
};

// Three whole calendar months that begin next month: in the future, so they add nothing to any month the closing specs use.
const next = addMonths(currentMonth(), 1);
const months = [next, addMonths(next, 1), addMonths(next, 2)];
const WINDOW = { start: firstDayOf(months[0]!), end: lastDateOf(months[2]!) };

test.describe("registering a campaign of three months", () => {
  test("calculates the split, shows what the backend registers and lists the campaign", async ({ financeSession: page, api }) => {
    const masters = await readMasterChoices(api);
    const name = uniqueCampaignName();
    await openNewCampaign(page);
    await fillCampaign(page, masters, { name, ...WINDOW, impressions: TOTAL, cpm: "1.00" });

    await calculateButton(page).click();

    await expect(page.getByRole("table").getByRole("row")).toHaveCount(months.length + 1);
    for (const month of months) await expect(page.getByRole("spinbutton", { name: `Volumen ${monthLabel(month)}`, exact: true })).toBeVisible();
    const shown = await shownVolumes(page);
    const sum = shown.reduce((total, volume) => total + volume, 0);
    expect(sum).toBe(TOTAL);
    await expect(page.getByText(`Suma ${sum} de ${TOTAL}`, { exact: true })).toBeVisible();

    const responded = waitForRegistration(page);
    await submitButton(page).click();
    const response = await responded;

    expect(response.status(), "the registration").toBe(201);
    const registered = (await response.json()) as RegisteredCampaign;
    expect(registered.lines).toHaveLength(1);
    const flights = registered.lines[0]?.flights ?? [];
    expect(flights).toHaveLength(months.length);
    expect(flights.map((flight) => ({ year: flight.period_year, month: flight.period_month }))).toEqual(months);
    expect(flights.map((flight) => flight.contracted_impressions)).toEqual(shown);
    expect(flights.reduce((total, flight) => total + flight.contracted_impressions, 0)).toBe(TOTAL);

    await page.waitForURL(/\/campaigns\?success=true/);
    const listed = ((await (await api.get("campaigns")).json()) as RegisteredCampaign[]).find((campaign) => campaign.name === name);
    expect(listed, "the campaign in GET /api/campaigns").toBeDefined();
    expect(listed?.start_date).toBe(WINDOW.start);
    expect(listed?.end_date).toBe(WINDOW.end);
  });

  test("a line with its own dates shows only the months it touches", async ({ financeSession: page, api }) => {
    const masters = await readMasterChoices(api);
    await openNewCampaign(page);
    await fillCampaign(page, masters, { name: uniqueCampaignName(), ...WINDOW, impressions: TOTAL, cpm: "1.00" });
    const touched = [months[1]!, months[2]!];

    await page.getByLabel("Heredar las fechas de la campaña", { exact: true }).uncheck();
    await page.getByLabel("Inicio de la línea", { exact: true }).fill(isoDate(touched[0]!.year, touched[0]!.month, 10));
    await page.getByLabel("Fin de la línea", { exact: true }).fill(isoDate(touched[1]!.year, touched[1]!.month, 20));
    await calculateButton(page).click();

    await expect(volumeFields(page)).toHaveCount(touched.length);
    for (const month of touched) await expect(page.getByRole("spinbutton", { name: `Volumen ${monthLabel(month)}`, exact: true })).toBeVisible();
    await expect(page.getByRole("spinbutton", { name: `Volumen ${monthLabel(months[0]!)}`, exact: true })).toHaveCount(0);
    expect((await shownVolumes(page)).reduce((total, volume) => total + volume, 0)).toBe(TOTAL);
  });
});

test.describe("what the form refuses before sending", () => {
  test("a manual split that does not add up blocks the submission, and the reset restores the proportional one", async ({ financeSession: page, api }) => {
    const masters = await readMasterChoices(api);
    const registrations = countRegistrations(page);
    await openNewCampaign(page);
    await fillCampaign(page, masters, { name: uniqueCampaignName(), ...WINDOW, impressions: TOTAL, cpm: "1.00" });
    await calculateButton(page).click();
    await expect(volumeFields(page)).toHaveCount(months.length);
    const initial = await shownVolumes(page);

    await volumeFields(page).first().fill(String((initial[0] ?? 0) + 1));
    await expect(page.getByText("Reparto manual", { exact: true })).toBeVisible();
    await submitButton(page).click();

    await expect(appAlert(page).filter({ hasText: MESSAGES.fix })).toBeVisible();
    await expect(appAlert(page).filter({ hasText: MESSAGES.mismatch }).first()).toBeVisible();
    expect(registrations.count(), "registrations sent while the split did not add up").toBe(0);

    await page.getByRole("button", { name: "Restablecer reparto proporcional", exact: true }).click();
    expect(await shownVolumes(page)).toEqual(initial);
    await expect(page.getByText("Reparto manual", { exact: true })).toHaveCount(0);
    expect(registrations.count(), "registrations sent during the whole case").toBe(0);
  });

  test("a negative CPM shows its message and sends nothing", async ({ financeSession: page, api }) => {
    const masters = await readMasterChoices(api);
    const registrations = countRegistrations(page);
    await openNewCampaign(page);
    await fillCampaign(page, masters, { name: uniqueCampaignName(), ...WINDOW, impressions: TOTAL, cpm: "-1" });

    await submitButton(page).click();

    await expect(appAlert(page).filter({ hasText: MESSAGES.fix })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "CPM (venta) *", exact: true })).toHaveAccessibleDescription(MESSAGES.negativeCpm);
    expect(registrations.count()).toBe(0);
  });

  test("line dates outside the campaign's are refused in the browser, beside the line", async ({ financeSession: page, api }) => {
    const masters = await readMasterChoices(api);
    const registrations = countRegistrations(page);
    await openNewCampaign(page);
    await fillCampaign(page, masters, { name: uniqueCampaignName(), ...WINDOW, impressions: TOTAL, cpm: "1.00" });
    const before = addMonths(months[0]!, -1);

    await page.getByLabel("Heredar las fechas de la campaña", { exact: true }).uncheck();
    await page.getByLabel("Inicio de la línea", { exact: true }).fill(lastDateOf(before));
    await page.getByLabel("Fin de la línea", { exact: true }).fill(isoDate(months[1]!.year, months[1]!.month, 10));
    await submitButton(page).click();

    await expect(page.getByLabel("Inicio de la línea", { exact: true })).toHaveAccessibleDescription(MESSAGES.startOutside);
    expect(registrations.count()).toBe(0);
  });
});

test.describe("what the backend refuses, shown beside the line", () => {
  test("a volume too small for its months shows volume_too_small_for_flights in Spanish in the line", async ({ financeSession: page, api }) => {
    const masters = await readMasterChoices(api);
    const registrations = countRegistrations(page);
    // The code comes from the backend: ask it directly, then see the screen say the same thing in Spanish.
    const direct = await api.post("flights/preview", {
      data: { campaign_start_date: WINDOW.start, campaign_end_date: WINDOW.end, contracted_impressions: 1 },
    });
    expect(direct.status()).toBe(422);
    expect(JSON.stringify(await direct.json())).toContain("volume_too_small_for_flights");

    await openNewCampaign(page);
    await fillCampaign(page, masters, { name: uniqueCampaignName(), ...WINDOW, impressions: 1, cpm: "1.00" });
    await calculateButton(page).click();

    const lines = page.getByRole("group", { name: "Líneas de campaña" });
    await expect(lines.getByRole("alert").filter({ hasText: MESSAGES.tooSmall })).toBeVisible();
    await expect(page.getByText(MESSAGES.genericPreview)).toHaveCount(0);
    expect(registrations.count()).toBe(0);
  });
});

test.describe("a campaign without a price (needs a previous month that is still open)", () => {
  test("CPM 0 registers, and the margin of the previous month labels it «Sin venta» with a dash", async ({ financeSession: page, api }) => {
    const previous = previousMonth();
    const month = currentMonth();
    const margin = await readMargin(api, previous);
    test.skip(
      flightsOf(margin).some((flight) => flight.state === "closed"),
      "el mes anterior ya tiene flights cerrados: no se registra una campaña que empiece en él; ejecuta reset-data.sh",
    );
    const masters = await readMasterChoices(api);
    const name = uniqueCampaignName();
    await openNewCampaign(page);
    // From the first day of the previous month, so that its first flight has already begun.
    await fillCampaign(page, masters, { name, start: firstDayOf(previous), end: lastDateOf(month), impressions: TOTAL, cpm: "0" });

    const responded = waitForRegistration(page);
    await submitButton(page).click();
    expect((await responded).status(), "the registration with CPM 0").toBe(201);
    await page.waitForURL(/\/campaigns\?success=true/);

    const afterRegistration = await readMargin(api, previous);
    const ours = afterRegistration.campaigns.find((campaign) => campaign.name === name);
    expect(ours, "the campaign in GET /api/margin of the previous month").toBeDefined();
    if (ours === undefined) return;
    const apiFlights = ours.lines.flatMap((line) => line.flights);
    expect(apiFlights.length).toBeGreaterThan(0);
    expect(apiFlights.every((flight) => flight.zero_sale && flight.margin_pct === null)).toBe(true);

    await page.goto("/margin");
    await chooseMonth(page, previous);
    await openAllCards(page, { campaigns: [ours] });
    for (const line of ours.lines) {
      const table = flightsTable(page, ours, line);
      for (const [index] of line.flights.entries()) {
        await expect(await flightCell(table, index, "Avisos")).toContainText("Sin venta");
        await expect(await flightCell(table, index, "% de margen")).toHaveText(percent(null));
      }
    }
    await expect(campaignCard(page, name)).toBeVisible();
  });
});
