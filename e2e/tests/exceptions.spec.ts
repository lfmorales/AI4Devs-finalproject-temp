import { appAlert } from "../support/alerts";
import {
  ALREADY_RESOLVED, counter, GENERIC_RESOLVE_FAILURE, HISTORY_WARNING, LINK_TARGET_CAMPAIGN, mappedLineOf, NO_MATCH_TEXT, openRow,
  openTab, plain, queueTable, readExceptions, readUnmappedLines, searchBox, seededLinkTarget, seededOpenUnmatched, TYPE_OPTION,
  typeSelect, type IngestionException,
} from "../support/exceptions";
import { expect, failApiCalls, test } from "../support/fixtures";
import { FRESH_DATABASE_SKIP_REASON } from "../support/margin";

// The first two blocks only read. The three cases that change the state each use one of the three seeded open
// unmatched rows, so they come last and run in this order (one worker, no parallelism).

const dspText = (row: IngestionException): string => `DSP ${row.dsp_id}`;
const searchableOf = (row: IngestionException): string =>
  plain([row.campaign_name, row.line_item_name, row.dsp_id === null ? null : dspText(row), row.external_campaign_id, row.external_line_item_id].filter((part) => part !== null).join(" "));

test.describe("the exception queue, reading", () => {
  test("«Abiertas» has the rows of GET /api/ingestion-exceptions?status=open", async ({ financeSession: page, api }) => {
    const open = await readExceptions(api, "open");
    test.skip(open.length === 0, "la cola no tiene excepciones abiertas: ejecuta reset-data.sh");

    await page.goto("/exceptions");

    await expect(queueTable(page).getByRole("row")).toHaveCount(open.length + 1);
    for (const row of open) await expect(openRow(page, row.id)).toHaveCount(1);
    await expect(counter(page, open.length, open.length)).toBeVisible();
  });

  test("«Resueltas» shows the resolved rows of the API with their note", async ({ financeSession: page, api }) => {
    const resolved = await readExceptions(api, "resolved");
    const withNote = resolved.filter((row) => row.note !== null);
    test.skip(withNote.length === 0, "no hay excepciones resueltas con nota: ejecuta reset-data.sh");

    await page.goto("/exceptions");
    await openTab(page, "Resueltas");

    await expect(queueTable(page).getByRole("row")).toHaveCount(resolved.length + 1);
    for (const row of withNote) await expect(queueTable(page).getByRole("row").filter({ hasText: row.note ?? "" })).toHaveCount(1);
  });

  test.describe("the filter", () => {
    test("finds by catalogue name without accents or case", async ({ financeSession: page, api }) => {
      const open = await readExceptions(api, "open");
      const term = "catalogo linea";
      const expected = open.filter((row) => searchableOf(row).includes(term));
      test.skip(expected.length === 0, FRESH_DATABASE_SKIP_REASON);
      // The check is only worth something if both spellings are in the queue.
      expect(expected.some((row) => /[^\u0000-\u007f]/.test(`${row.campaign_name} ${row.line_item_name}`))).toBe(true);
      expect(expected.some((row) => !/[^\u0000-\u007f]/.test(`${row.campaign_name} ${row.line_item_name}`))).toBe(true);

      await page.goto("/exceptions");
      for (const typed of ["catalogo linea", "CATÁLOGO LÍNEA", "Catálogo Linea"]) {
        await searchBox(page).fill(typed);
        await expect(queueTable(page).getByRole("row")).toHaveCount(expected.length + 1);
        await expect(counter(page, expected.length, open.length)).toBeVisible();
        for (const row of expected) await expect(openRow(page, row.id)).toHaveCount(1);
      }
    });

    test("finds by external pair and by DSP", async ({ financeSession: page, api }) => {
      const open = await readExceptions(api, "open");
      const withPair = open.find((row) => row.external_campaign_id !== null);
      const withDsp = open.find((row) => row.dsp_id !== null);
      test.skip(withPair === undefined || withDsp === undefined, FRESH_DATABASE_SKIP_REASON);
      if (withPair === undefined || withDsp === undefined) return;

      await page.goto("/exceptions");

      const pairTerm = withPair.external_campaign_id ?? "";
      const byPair = open.filter((row) => searchableOf(row).includes(plain(pairTerm)));
      await searchBox(page).fill(pairTerm);
      await expect(queueTable(page).getByRole("row")).toHaveCount(byPair.length + 1);
      await expect(counter(page, byPair.length, open.length)).toBeVisible();
      await expect(openRow(page, withPair.id)).toHaveCount(1);

      const dspTerm = dspText(withDsp);
      const byDsp = open.filter((row) => row.dsp_id !== null && plain(dspText(row)).includes(plain(dspTerm)));
      await searchBox(page).fill(dspTerm);
      await expect(queueTable(page).getByRole("row")).toHaveCount(byDsp.length + 1);
      await expect(counter(page, byDsp.length, open.length)).toBeVisible();
    });

    test("shows the no-match state, and «Limpiar filtros» brings every row back", async ({ financeSession: page, api }) => {
      const open = await readExceptions(api, "open");
      test.skip(open.length === 0, FRESH_DATABASE_SKIP_REASON);

      await page.goto("/exceptions");
      await searchBox(page).fill(`E2E-SIN-COINCIDENCIA-${Date.now()}`);

      await expect(page.getByText(NO_MATCH_TEXT)).toBeVisible();
      await expect(counter(page, 0, open.length)).toBeVisible();
      await expect(queueTable(page)).toHaveCount(0);

      await page.getByRole("button", { name: "Limpiar filtros" }).click();
      await expect(searchBox(page)).toHaveValue("");
      await expect(queueTable(page).getByRole("row")).toHaveCount(open.length + 1);
    });

    test("the type selector keeps only the chosen type", async ({ financeSession: page, api }) => {
      const open = await readExceptions(api, "open");
      test.skip(open.length === 0, FRESH_DATABASE_SKIP_REASON);

      await page.goto("/exceptions");

      for (const type of ["unmatched_delivery", "missing_delivery"] as const) {
        const expected = open.filter((row) => row.exception_type === type);
        await typeSelect(page).selectOption({ label: TYPE_OPTION[type] });
        await expect(counter(page, expected.length, open.length)).toBeVisible();
        if (expected.length > 0) {
          await expect(queueTable(page).getByRole("row")).toHaveCount(expected.length + 1);
          for (const row of expected) await expect(openRow(page, row.id)).toHaveCount(1);
        }
      }
      await typeSelect(page).selectOption({ label: "Todas" });
      await expect(counter(page, open.length, open.length)).toBeVisible();
    });
  });
});

test.describe("the exception queue, failures", () => {
  test("shows 'Acceso denegado' and drops the Excepciones link when the queue answers 403", async ({ financeSession: page }) => {
    await failApiCalls(page, "/ingestion-exceptions", 403);

    await page.goto("/exceptions");

    await expect(page.getByRole("heading", { name: "Acceso denegado" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Principal" }).getByRole("link", { name: "Excepciones" })).toHaveCount(0);
  });
});

test.describe("the exception queue, changing state (needs a freshly seeded database)", () => {
  test("resolving an open row with a note takes it out of «Abiertas» without reloading", async ({ financeSession: page, api }) => {
    const [target] = await seededOpenUnmatched(api);
    test.skip(target === undefined, FRESH_DATABASE_SKIP_REASON);
    if (target === undefined) return;
    const openBefore = await readExceptions(api, "open");
    const note = `E2E-NOTA-${Date.now()}`;

    await page.goto("/exceptions");
    await expect(openRow(page, target.id)).toHaveCount(1);
    await page.evaluate(() => { (window as unknown as { e2eStillLoaded: boolean }).e2eStillLoaded = true; });

    await page.getByRole("button", { name: `Resolver excepción ${target.id}`, exact: true }).click();
    const dialog = page.getByRole("dialog", { name: `Resolver excepción ${target.id}` });
    await dialog.getByRole("textbox", { name: "Nota (opcional)" }).fill(note);
    await dialog.getByRole("button", { name: "Confirmar resolución" }).click();

    await expect(page.getByRole("status").filter({ hasText: `Excepción ${target.id} resuelta.` })).toBeVisible();
    await expect(openRow(page, target.id)).toHaveCount(0);
    await expect(queueTable(page).getByRole("row")).toHaveCount(openBefore.length);
    expect(await page.evaluate(() => (window as unknown as { e2eStillLoaded?: boolean }).e2eStillLoaded)).toBe(true);

    const resolved = (await readExceptions(api, "resolved")).find((row) => row.id === target.id);
    expect(resolved?.status).toBe("resolved");
    expect(resolved?.note).toBe(note);
    expect((await readExceptions(api, "open")).some((row) => row.id === target.id)).toBe(false);
  });

  test("linking an unmatched row to the unmapped line of the demo campaign maps it and warns about the history", async ({ financeSession: page, api }) => {
    const [target] = await seededOpenUnmatched(api);
    const line = await seededLinkTarget(api);
    test.skip(target === undefined || line === undefined, FRESH_DATABASE_SKIP_REASON);
    if (target === undefined || line === undefined) return;
    const unmappedBefore = await readUnmappedLines(api);
    expect(await mappedLineOf(api, target.external_campaign_id ?? "", target.external_line_item_id ?? "")).toBeNull();

    await page.goto("/exceptions");
    await page.getByRole("button", { name: `Vincular a una línea (excepción ${target.id})`, exact: true }).click();
    const dialog = page.getByRole("dialog", { name: `Vincular la excepción ${target.id} a una línea` });

    // The dialog offers exactly the lines the API says have no mapping.
    await expect(dialog.getByRole("radiogroup", { name: "Líneas sin mapeo" }).getByRole("radio")).toHaveCount(unmappedBefore.length);
    const choice = dialog.getByRole("radio", { name: new RegExp(`^${LINK_TARGET_CAMPAIGN}, línea ${line.line_number}, `) });
    await choice.check();
    await dialog.getByRole("button", { name: "Confirmar vinculación" }).click();

    await expect(openRow(page, target.id)).toHaveCount(0);
    await expect(page.getByRole("status").filter({ hasText: `Excepción ${target.id} vinculada a ${LINK_TARGET_CAMPAIGN}, línea ${line.line_number}` })).toBeVisible();
    await expect(appAlert(page).filter({ hasText: HISTORY_WARNING })).toBeVisible();

    expect((await readExceptions(api, "resolved")).find((row) => row.id === target.id)?.status).toBe("resolved");
    expect(await mappedLineOf(api, target.external_campaign_id ?? "", target.external_line_item_id ?? "")).toBe(line.id);
    expect((await readUnmappedLines(api)).some((entry) => entry.id === line.id)).toBe(false);
  });

  test("a row resolved through the API before the confirmation shows the error in Spanish, not a generic one", async ({ financeSession: page, api }) => {
    const [target] = await seededOpenUnmatched(api);
    test.skip(target === undefined, FRESH_DATABASE_SKIP_REASON);
    if (target === undefined) return;

    await page.goto("/exceptions");
    await expect(openRow(page, target.id)).toHaveCount(1);
    await page.getByRole("button", { name: `Resolver excepción ${target.id}`, exact: true }).click();
    const dialog = page.getByRole("dialog", { name: `Resolver excepción ${target.id}` });

    const first = await api.post(`ingestion-exceptions/${target.id}/resolve`, { data: { note: null } });
    expect(first.status(), "the resolution made behind the screen's back").toBe(200);
    await dialog.getByRole("button", { name: "Confirmar resolución" }).click();

    await expect(appAlert(page).filter({ hasText: ALREADY_RESOLVED })).toBeVisible();
    await expect(page.getByText(GENERIC_RESOLVE_FAILURE)).toHaveCount(0);
    await expect(openRow(page, target.id)).toHaveCount(0);
  });
});
