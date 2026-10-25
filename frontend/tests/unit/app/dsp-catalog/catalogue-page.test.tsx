import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import DspCatalogPage from "@/app/(authenticated)/dsp-catalog/page";
import type { DspCatalogItem, DspCatalogPage as Page, DspMapping, UnmappedLine } from "@/lib/api/dsp-catalog";
import { installRoutes, plain, renderAuthenticated, reply, type FakeReply } from "../../../helpers/api-pages";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

const FIRST_PAGE = "GET /dsp-catalog?limit=50&offset=0";
const UNMAPPED = "GET /campaign-lines/unmapped";
const MAP_4 = "POST /campaign-lines/4/dsp-mappings";

const HISTORY_WARNING =
  "Esta línea empezó antes de la ventana de siete días. La entrega anterior no se carga sola: pide cargar el histórico con run_ingestion --from … --to …";

function item(overrides: Partial<DspCatalogItem> = {}): DspCatalogItem {
  return {
    dsp_id: 1, external_campaign_id: "C-1", external_line_item_id: "L-1", campaign_name: "Navidad 2026", line_item_name: "Display ES",
    line_start_date: "2026-12-01", line_end_date: "2026-12-31", first_seen_date: "2026-12-01", last_seen_date: "2026-12-20",
    last_impressions_date: "2026-12-19", mapped_line_id: null, ...overrides,
  };
}

function page(items: DspCatalogItem[], overrides: Partial<Page> = {}): Page {
  return { items, total: items.length, limit: 50, offset: 0, ...overrides };
}

const LINES: UnmappedLine[] = [
  { id: 4, campaign_name: "Campaña Navidad", line_number: 1, start_date: "2026-12-01", end_date: "2026-12-31", dsp_id: 1, dsp_name: "Adform" },
];

function mapping(overrides: Partial<DspMapping> = {}): DspMapping {
  return {
    id: 9, campaign_line_id: 4, dsp_id: 1, external_campaign_id: "C-1", external_line_item_id: "L-1",
    validated_at: "2026-12-21T09:00:00", validation: "found", last_impressions_date: "2026-12-19", needs_history_load: false, ...overrides,
  };
}

async function linkFirstRow(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Vincular a una línea: Navidad 2026 / Display ES" }));
  const dialog = await screen.findByRole("dialog", { name: "Vincular la pareja a una línea" });
  await user.click(await within(dialog).findByRole("radio", { name: /Campaña Navidad/ }));
  await user.click(within(dialog).getByRole("button", { name: "Confirmar vinculación" }));
  return dialog;
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe("the catalogue table", () => {
  it("asks for the first page of 50 and shows campaign, line, dates, last impressions date and whether it is linked", async () => {
    const requests = installRoutes({ [FIRST_PAGE]: () => reply(200, page([item(), item({ external_line_item_id: "L-2", line_item_name: "Video", mapped_line_id: 7, last_impressions_date: null, line_end_date: null })])) });

    renderAuthenticated(<DspCatalogPage />);

    const table = await screen.findByRole("table", { name: "Catálogo Adform" });
    const headers = within(table).getAllByRole("columnheader").map((h) => plain(h));
    expect(headers).toEqual(["Campaña", "Línea", "Fechas de la línea", "Última fecha con impresiones", "Vinculada", "Acciones"]);
    const rows = within(table).getAllByRole("row").slice(1).map((row) => within(row).getAllByRole("cell").map((cell) => plain(cell)));
    expect(rows[0]!.slice(0, 5)).toEqual(["Navidad 2026", "Display ES", "2026-12-01 – 2026-12-31", "2026-12-19", "No"]);
    expect(rows[1]!.slice(0, 5)).toEqual(["Navidad 2026", "Video", "2026-12-01 – —", "—", "Sí"]);
    expect(requests.map((r) => r.path)).toEqual(["/dsp-catalog?limit=50&offset=0"]);
  });

  it("shows no cost column and no external identifier", async () => {
    installRoutes({ [FIRST_PAGE]: () => reply(200, page([item()])) });

    renderAuthenticated(<DspCatalogPage />);

    await screen.findByRole("table", { name: "Catálogo Adform" });
    expect(document.body).not.toHaveTextContent("C-1");
    expect(document.body).not.toHaveTextContent(/coste|cost/i);
  });

  it("formats the shown range and total with grouping", async () => {
    installRoutes({ [FIRST_PAGE]: () => reply(200, page([item()], { total: 1234 })) });

    renderAuthenticated(<DspCatalogPage />);

    expect(await screen.findByText("Mostrando 1–1 de 1.234")).toBeInTheDocument();
  });

  it("keeps the labelled filter controls findable by label", async () => {
    installRoutes({ [FIRST_PAGE]: () => reply(200, page([item()])) });

    renderAuthenticated(<DspCatalogPage />);

    await screen.findByRole("table", { name: "Catálogo Adform" });
    expect(screen.getByLabelText("Buscar por nombre")).toBeInTheDocument();
    expect(screen.getByLabelText("Vinculación")).toBeInTheDocument();
    expect(screen.getByLabelText("Activas desde")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Filtrar" })).toBeInTheDocument();
  });
});

describe("the catalogue filters and pagination", () => {
  it("sends the text filter", async () => {
    const user = userEvent.setup();
    const requests = installRoutes({
      [FIRST_PAGE]: () => reply(200, page([item()])),
      "GET /dsp-catalog?q=navidad&limit=50&offset=0": () => reply(200, page([item()])),
    });
    renderAuthenticated(<DspCatalogPage />);
    await screen.findByRole("table", { name: "Catálogo Adform" });

    await user.type(screen.getByLabelText("Buscar por nombre"), "navidad");
    await user.click(screen.getByRole("button", { name: "Filtrar" }));

    await waitFor(() => expect(requests.at(-1)?.path).toBe("/dsp-catalog?q=navidad&limit=50&offset=0"));
  });

  it.each([["Vinculadas", "true"], ["Sin vincular", "false"]])("sends mapped=%s as %s", async (label, value) => {
    const user = userEvent.setup();
    const requests = installRoutes({
      [FIRST_PAGE]: () => reply(200, page([item()])),
      [`GET /dsp-catalog?mapped=${value}&limit=50&offset=0`]: () => reply(200, page([item()])),
    });
    renderAuthenticated(<DspCatalogPage />);
    await screen.findByRole("table", { name: "Catálogo Adform" });

    await user.selectOptions(screen.getByLabelText("Vinculación"), label);
    await user.click(screen.getByRole("button", { name: "Filtrar" }));

    await waitFor(() => expect(requests.at(-1)?.path).toBe(`/dsp-catalog?mapped=${value}&limit=50&offset=0`));
  });

  it("sends active_since, and all the filters together", async () => {
    const user = userEvent.setup();
    const all = "GET /dsp-catalog?q=ve&mapped=false&active_since=2026-12-01&limit=50&offset=0";
    const requests = installRoutes({ [FIRST_PAGE]: () => reply(200, page([item()])), [all]: () => reply(200, page([item()])) });
    renderAuthenticated(<DspCatalogPage />);
    await screen.findByRole("table", { name: "Catálogo Adform" });

    await user.type(screen.getByLabelText("Buscar por nombre"), "ve");
    await user.selectOptions(screen.getByLabelText("Vinculación"), "Sin vincular");
    await user.type(screen.getByLabelText("Activas desde"), "2026-12-01");
    await user.click(screen.getByRole("button", { name: "Filtrar" }));

    await waitFor(() => expect(requests.at(-1)?.path).toBe(all.replace("GET ", "")));
  });

  it("explains that «Activas desde» compares with the last date with a row in Adform, not real activity", async () => {
    installRoutes({ [FIRST_PAGE]: () => reply(200, page([item()])) });

    renderAuthenticated(<DspCatalogPage />);

    await screen.findByRole("table", { name: "Catálogo Adform" });
    expect(screen.getByLabelText("Activas desde")).toHaveAccessibleDescription(/última fecha con fila en Adform, no actividad real/);
  });

  it("pages with the offset, disables the buttons at both ends and shows the range", async () => {
    const user = userEvent.setup();
    const requests = installRoutes({
      [FIRST_PAGE]: () => reply(200, page([item()], { total: 120 })),
      "GET /dsp-catalog?limit=50&offset=50": () => reply(200, page([item({ line_item_name: "Segunda" })], { total: 120, offset: 50 })),
      "GET /dsp-catalog?limit=50&offset=100": () => reply(200, page(Array.from({ length: 20 }, (_, index) => item({ external_line_item_id: `L-${index}`, line_item_name: index === 0 ? "Tercera" : `Resto ${index}` })), { total: 120, offset: 100 })),
    });
    renderAuthenticated(<DspCatalogPage />);
    await screen.findByRole("table", { name: "Catálogo Adform" });
    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    expect(await screen.findByText("Segunda")).toBeInTheDocument();
    expect(requests.at(-1)?.path).toBe("/dsp-catalog?limit=50&offset=50");
    expect(screen.getByText("Mostrando 51–51 de 120")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    expect(await screen.findByText("Tercera")).toBeInTheDocument();
    expect(requests.at(-1)?.path).toBe("/dsp-catalog?limit=50&offset=100");
    expect(screen.getByRole("button", { name: "Siguiente" })).toBeDisabled();
  });

  it("goes back to the first page when a filter is applied", async () => {
    const user = userEvent.setup();
    const requests = installRoutes({
      [FIRST_PAGE]: () => reply(200, page([item()], { total: 120 })),
      "GET /dsp-catalog?limit=50&offset=50": () => reply(200, page([item({ line_item_name: "Segunda" })], { total: 120, offset: 50 })),
      "GET /dsp-catalog?q=x&limit=50&offset=0": () => reply(200, page([item()])),
    });
    renderAuthenticated(<DspCatalogPage />);
    await screen.findByRole("table", { name: "Catálogo Adform" });
    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    await screen.findByText("Segunda");

    await user.type(screen.getByLabelText("Buscar por nombre"), "x");
    await user.click(screen.getByRole("button", { name: "Filtrar" }));

    await waitFor(() => expect(requests.at(-1)?.path).toBe("/dsp-catalog?q=x&limit=50&offset=0"));
  });
});

describe("the catalogue states", () => {
  it("shows loading, and neither empty nor error, while the page is pending", async () => {
    installRoutes({ [FIRST_PAGE]: () => new Promise<FakeReply>(() => {}) });

    renderAuthenticated(<DspCatalogPage />);

    expect(await screen.findByText("Cargando catálogo…")).toBeInTheDocument();
    expect(screen.queryByText("No hay parejas que mostrar")).not.toBeInTheDocument();
    expect(screen.queryByText(/No se pudo cargar el catálogo/)).not.toBeInTheDocument();
  });

  it("shows the empty state, and not loading or error, when nothing matches", async () => {
    installRoutes({ [FIRST_PAGE]: () => reply(200, page([])) });

    renderAuthenticated(<DspCatalogPage />);

    expect(await screen.findByText("No hay parejas que mostrar")).toBeInTheDocument();
    expect(screen.queryByText("Cargando catálogo…")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows the error state, and not an empty catalogue, on a failure", async () => {
    installRoutes({ [FIRST_PAGE]: () => reply(500, { code: "internal_error", message: "x" }) });

    renderAuthenticated(<DspCatalogPage />);

    expect(await screen.findByText("No se pudo cargar el catálogo. Inténtalo de nuevo más tarde.")).toBeInTheDocument();
    expect(screen.queryByText("No hay parejas que mostrar")).not.toBeInTheDocument();
  });

  it("shows the session-expired page on a 401", async () => {
    installRoutes({ [FIRST_PAGE]: () => reply(401, { code: "invalid_token", message: "x" }) });

    renderAuthenticated(<DspCatalogPage />);

    await waitFor(() => expect(screen.getByText("Sesión caducada")).toBeInTheDocument());
  });

  it("shows the access-denied page to a user without the operations role", async () => {
    installRoutes({ [FIRST_PAGE]: () => reply(403, { code: "missing_role", message: "x" }) });

    renderAuthenticated(<DspCatalogPage />);

    await waitFor(() => expect(screen.getByText("Acceso denegado")).toBeInTheDocument());
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("linking a pair from the catalogue", () => {
  it("offers the button on unlinked rows only", async () => {
    installRoutes({ [FIRST_PAGE]: () => reply(200, page([item(), item({ line_item_name: "Video", mapped_line_id: 7 })])) });

    renderAuthenticated(<DspCatalogPage />);

    expect(await screen.findByRole("button", { name: "Vincular a una línea: Navidad 2026 / Display ES" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Vincular a una línea: Navidad 2026 \/ Video/ })).not.toBeInTheDocument();
  });

  it("posts the row's own pair for the chosen line, showing no identifier anywhere", async () => {
    const user = userEvent.setup();
    const requests = installRoutes({
      [FIRST_PAGE]: () => reply(200, page([item()])), [UNMAPPED]: () => reply(200, LINES), [MAP_4]: () => reply(201, mapping()),
    });
    renderAuthenticated(<DspCatalogPage />);

    await linkFirstRow(user);

    await screen.findByText("Adform confirma la pareja.");
    expect(requests.find((r) => r.method === "POST")?.body).toEqual({ external_campaign_id: "C-1", external_line_item_id: "L-1" });
    expect(document.body).not.toHaveTextContent("C-1");
    expect(document.body).not.toHaveTextContent("L-1");
  });

  it("marks the row as linked without reloading the catalogue", async () => {
    const user = userEvent.setup();
    const requests = installRoutes({
      [FIRST_PAGE]: () => reply(200, page([item()])), [UNMAPPED]: () => reply(200, LINES), [MAP_4]: () => reply(201, mapping()),
    });
    renderAuthenticated(<DspCatalogPage />);

    await linkFirstRow(user);

    await waitFor(() => expect(screen.queryByRole("button", { name: /^Vincular a una línea:/ })).not.toBeInTheDocument());
    const row = within(screen.getByRole("table", { name: "Catálogo Adform" })).getAllByRole("row")[1]!;
    expect(plain(within(row).getAllByRole("cell")[4]!)).toBe("Sí");
    expect(requests.filter((r) => r.path.startsWith("/dsp-catalog"))).toHaveLength(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it.each([
    ["found", "Adform confirma la pareja."],
    ["unknown", "Adform no reconoce esta pareja."],
    ["unreachable", "No se pudo consultar Adform para validar la pareja."],
  ] as const)("shows the validation %s in Spanish", async (validation, message) => {
    const user = userEvent.setup();
    installRoutes({
      [FIRST_PAGE]: () => reply(200, page([item()])), [UNMAPPED]: () => reply(200, LINES), [MAP_4]: () => reply(201, mapping({ validation })),
    });
    renderAuthenticated(<DspCatalogPage />);

    await linkFirstRow(user);

    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it("warns that no recent delivery is recorded when last_impressions_date is null", async () => {
    const user = userEvent.setup();
    installRoutes({
      [FIRST_PAGE]: () => reply(200, page([item()])), [UNMAPPED]: () => reply(200, LINES),
      [MAP_4]: () => reply(201, mapping({ last_impressions_date: null })),
    });
    renderAuthenticated(<DspCatalogPage />);

    await linkFirstRow(user);

    expect(await screen.findByText("No consta entrega reciente de esta pareja")).toBeInTheDocument();
  });

  it("does not warn about recent delivery when there is a last_impressions_date", async () => {
    const user = userEvent.setup();
    installRoutes({
      [FIRST_PAGE]: () => reply(200, page([item()])), [UNMAPPED]: () => reply(200, LINES), [MAP_4]: () => reply(201, mapping()),
    });
    renderAuthenticated(<DspCatalogPage />);

    await linkFirstRow(user);

    await screen.findByText("Adform confirma la pareja.");
    expect(screen.queryByText("No consta entrega reciente de esta pareja")).not.toBeInTheDocument();
  });

  it("shows the history warning, with no action, when the line needs a history load", async () => {
    const user = userEvent.setup();
    installRoutes({
      [FIRST_PAGE]: () => reply(200, page([item()])), [UNMAPPED]: () => reply(200, LINES),
      [MAP_4]: () => reply(201, mapping({ needs_history_load: true })),
    });
    renderAuthenticated(<DspCatalogPage />);

    await linkFirstRow(user);

    expect(await screen.findByText(HISTORY_WARNING, { exact: false })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /histórico/i })).not.toBeInTheDocument();
  });

  it.each([
    [409, "duplicate_dsp_mapping", "Esta pareja de identificadores ya está vinculada a una línea."],
    [404, "campaign_line_not_found", "La línea elegida ya no existe."],
    [422, "dsp_not_supported", "El DSP de la línea elegida todavía no tiene conector."],
  ])("shows %i %s in Spanish inside the dialog and keeps the row unlinked", async (status, code, message) => {
    const user = userEvent.setup();
    installRoutes({
      [FIRST_PAGE]: () => reply(200, page([item()])), [UNMAPPED]: () => reply(200, LINES),
      [MAP_4]: () => reply(status, { code, message: "Backend text in English" }),
    });
    renderAuthenticated(<DspCatalogPage />);

    const dialog = await linkFirstRow(user);

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(message);
    expect(screen.queryByText(/Backend text/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Vincular a una línea: Navidad 2026 / Display ES" })).toBeInTheDocument();
  });

  it("shows a generic Spanish message on any other failure", async () => {
    const user = userEvent.setup();
    installRoutes({
      [FIRST_PAGE]: () => reply(200, page([item()])), [UNMAPPED]: () => reply(200, LINES),
      [MAP_4]: () => reply(500, { code: "internal_error", message: "boom" }),
    });
    renderAuthenticated(<DspCatalogPage />);

    const dialog = await linkFirstRow(user);

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("No se pudo vincular la pareja. Inténtalo de nuevo.");
  });

  it.each([[401, "Sesión caducada"], [403, "Acceso denegado"]])("shows the matching page when the link gets a %i", async (status, text) => {
    const user = userEvent.setup();
    installRoutes({
      [FIRST_PAGE]: () => reply(200, page([item()])), [UNMAPPED]: () => reply(200, LINES),
      [MAP_4]: () => reply(status, { code: "x", message: "x" }),
    });
    renderAuthenticated(<DspCatalogPage />);

    await linkFirstRow(user);

    await waitFor(() => expect(screen.getByText(text)).toBeInTheDocument());
  });
});
