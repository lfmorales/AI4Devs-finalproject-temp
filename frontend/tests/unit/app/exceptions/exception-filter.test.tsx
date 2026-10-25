import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ExceptionsPage from "@/app/(authenticated)/exceptions/page";
import type { IngestionException } from "@/lib/api/exceptions";
import { installRoutes, renderAuthenticated, reply } from "../../../helpers/api-pages";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

const OPEN = "GET /ingestion-exceptions?status=open";
const RESOLVED = "GET /ingestion-exceptions?status=resolved";

function exception(overrides: Partial<IngestionException> = {}): IngestionException {
  return {
    id: 1, exception_type: "unmatched_delivery", status: "open", ingestion_batch_id: 3, dsp_id: 1,
    external_campaign_id: "C-9", external_line_item_id: "L-9", campaign_line_id: null, campaign_period_id: null,
    first_date: "2026-08-03", last_date: "2026-08-08", days: 3, impressions_total: 40, clicks_total: 1,
    resolved_at: null, resolved_by: null, note: null, campaign_name: "Campaña Navidad", line_item_name: "Display Móvil", ...overrides,
  };
}

const NAVIDAD = exception();
const VERANO = exception({ id: 2, dsp_id: 2, external_campaign_id: "K-1", external_line_item_id: "M-2", campaign_name: "Verano", line_item_name: "Vídeo" });
const AUSENCIA = exception({
  id: 3, exception_type: "missing_delivery", dsp_id: null, external_campaign_id: null, external_line_item_id: null,
  campaign_line_id: 17, campaign_period_id: 4, campaign_name: null, line_item_name: null,
});
const QUEUE = [NAVIDAD, VERANO, AUSENCIA];

async function renderQueue(rows = QUEUE, extra: Record<string, () => ReturnType<typeof reply>> = {}) {
  const requests = installRoutes({ [OPEN]: () => reply(200, rows), ...extra });
  renderAuthenticated(<ExceptionsPage />);
  await screen.findByRole("table", { name: "Cola de excepciones" });
  return requests;
}

const search = () => screen.getByLabelText("Buscar excepciones");
const shownIds = () => within(screen.getByRole("table", { name: "Cola de excepciones" })).queryAllByRole("button", { name: /^Resolver excepción/ })
  .map((button) => Number(/\d+/.exec(button.getAttribute("aria-label") ?? "")![0]));

beforeEach(() => vi.clearAllMocks());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("the exception queue filter", () => {
  it("offers a labelled search box and a «Tipo» selector with its three options", async () => {
    await renderQueue();

    expect(search()).toBeInTheDocument();
    const type = screen.getByLabelText("Tipo");
    expect(within(type).getAllByRole("option").map((option) => option.textContent)).toEqual(["Todas", "Entrega sin casar", "Ausencia"]);
  });

  it("shows every row and «Mostrando 3 de 3» before any filtering", async () => {
    await renderQueue();

    expect(shownIds()).toEqual([1, 2, 3]);
    expect(screen.getByText("Mostrando 3 de 3")).toBeInTheDocument();
  });

  it.each([
    ["the campaign name", "navidad", [1]],
    ["the line item name", "vídeo", [2]],
    ["the external pair", "K-1 / M-2", [2]],
    ["the DSP", "DSP 2", [2]],
    ["the absence text", "línea 17", [3]],
  ])("finds a row by %s", async (_label, text, expected) => {
    const user = userEvent.setup();
    await renderQueue();

    await user.type(search(), text);

    expect(shownIds()).toEqual(expected);
    expect(screen.getByText(`Mostrando ${expected.length} de 3`)).toBeInTheDocument();
  });

  it("ignores case and accents", async () => {
    const user = userEvent.setup();
    await renderQueue();

    await user.type(search(), "CAMPANA MOVIL");

    expect(shownIds()).toEqual([1]);
  });

  it("needs every term to match", async () => {
    const user = userEvent.setup();
    await renderQueue();

    await user.type(search(), "display navidad");
    expect(shownIds()).toEqual([1]);

    await user.type(search(), " verano");
    expect(screen.getByText("No hay excepciones que coincidan con la búsqueda")).toBeInTheDocument();
  });

  it("filters by type", async () => {
    const user = userEvent.setup();
    await renderQueue();

    await user.selectOptions(screen.getByLabelText("Tipo"), "Ausencia");
    expect(shownIds()).toEqual([3]);
    expect(screen.getByText("Mostrando 1 de 3")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Tipo"), "Entrega sin casar");
    expect(shownIds()).toEqual([1, 2]);
  });

  it("clears the text and the type with «Limpiar filtros»", async () => {
    const user = userEvent.setup();
    await renderQueue();
    await user.type(search(), "navidad");
    await user.selectOptions(screen.getByLabelText("Tipo"), "Entrega sin casar");

    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }));

    expect(search()).toHaveValue("");
    expect(screen.getByLabelText("Tipo")).toHaveValue("");
    expect(shownIds()).toEqual([1, 2, 3]);
    expect(screen.getByText("Mostrando 3 de 3")).toBeInTheDocument();
  });

  it("has «Limpiar filtros» disabled while there is nothing to clear", async () => {
    const user = userEvent.setup();
    await renderQueue();
    expect(screen.getByRole("button", { name: "Limpiar filtros" })).toBeDisabled();

    await user.type(search(), "x");

    expect(screen.getByRole("button", { name: "Limpiar filtros" })).toBeEnabled();
  });

  it("says nothing matches, and not that the queue is empty or loading, when the filter finds nothing", async () => {
    const user = userEvent.setup();
    await renderQueue();

    await user.type(search(), "zzz");

    expect(screen.getByText("No hay excepciones que coincidan con la búsqueda")).toBeInTheDocument();
    expect(screen.queryByText("No hay excepciones abiertas")).not.toBeInTheDocument();
    expect(screen.queryByText("Cargando excepciones…")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText("Mostrando 0 de 3")).toBeInTheDocument();
    expect(search()).toBeInTheDocument();
  });

  it("keeps saying the queue is empty, with no filter, when there is nothing at all", async () => {
    installRoutes({ [OPEN]: () => reply(200, []) });
    renderAuthenticated(<ExceptionsPage />);

    expect(await screen.findByText("No hay excepciones abiertas")).toBeInTheDocument();
    expect(screen.queryByText("No hay excepciones que coincidan con la búsqueda")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Buscar excepciones")).not.toBeInTheDocument();
  });
});

describe("the filter state", () => {
  it("makes no request when typing or choosing a type", async () => {
    const user = userEvent.setup();
    const requests = await renderQueue();

    await user.type(search(), "navidad");
    await user.selectOptions(screen.getByLabelText("Tipo"), "Ausencia");
    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }));

    expect(requests.map((request) => request.path)).toEqual(["/ingestion-exceptions?status=open"]);
  });

  it("keeps the text and the type when the tab changes, and applies them to the other list", async () => {
    const user = userEvent.setup();
    await renderQueue(QUEUE, { [RESOLVED]: () => reply(200, [exception({ id: 8, status: "resolved" }), exception({ id: 9, status: "resolved", campaign_name: "Otra", line_item_name: "Cosa" })]) });
    await user.type(search(), "navidad");
    await user.selectOptions(screen.getByLabelText("Tipo"), "Entrega sin casar");

    await user.click(screen.getByRole("tab", { name: "Resueltas" }));
    await screen.findByRole("table", { name: "Cola de excepciones" });

    expect(search()).toHaveValue("navidad");
    expect(screen.getByLabelText("Tipo")).toHaveValue("unmatched_delivery");
    expect(screen.getByText("Mostrando 1 de 2")).toBeInTheDocument();
    expect(screen.getByText("Campaña Navidad")).toBeInTheDocument();
    expect(screen.queryByText("Otra")).not.toBeInTheDocument();
  });

  it("removes a resolved row, lowers the counter and keeps the filter", async () => {
    const user = userEvent.setup();
    await renderQueue([NAVIDAD, exception({ id: 4, campaign_name: "Navidad bis" }), VERANO], {
      "POST /ingestion-exceptions/1/resolve": () => reply(200, exception({ status: "resolved" })),
    });
    await user.type(search(), "navidad");
    expect(screen.getByText("Mostrando 2 de 3")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Resolver excepción 1" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Confirmar resolución" }));

    await waitFor(() => expect(shownIds()).toEqual([4]));
    expect(screen.getByText("Mostrando 1 de 2")).toBeInTheDocument();
    expect(search()).toHaveValue("navidad");
  });

  it("removes a linked row, lowers the counter and keeps the filter", async () => {
    const user = userEvent.setup();
    await renderQueue(QUEUE, {
      "GET /campaign-lines/unmapped": () => reply(200, [{ id: 4, campaign_name: "Campaña", line_number: 1, start_date: "2026-12-01", end_date: "2026-12-31", dsp_id: 1, dsp_name: "Adform" }]),
      "POST /ingestion-exceptions/2/link": () => reply(200, {
        mapping: { id: 9, campaign_line_id: 4, dsp_id: 2, external_campaign_id: "K-1", external_line_item_id: "M-2", validated_at: "2026-08-10T09:00:00" },
        exception: { ...VERANO, status: "resolved" }, needs_history_load: false,
      }),
    });
    await user.selectOptions(screen.getByLabelText("Tipo"), "Entrega sin casar");
    expect(screen.getByText("Mostrando 2 de 3")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Vincular a una línea (excepción 2)" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(await within(dialog).findByRole("radio", { name: /Campaña/ }));
    await user.click(within(dialog).getByRole("button", { name: "Confirmar vinculación" }));

    await waitFor(() => expect(shownIds()).toEqual([1]));
    expect(screen.getByText("Mostrando 1 de 2")).toBeInTheDocument();
    expect(screen.getByLabelText("Tipo")).toHaveValue("unmatched_delivery");
  });

  it("keeps the searched text out of the URL and out of the browser storage", async () => {
    const user = userEvent.setup();
    await renderQueue();

    await user.type(search(), "secretoXYZ");
    await user.selectOptions(screen.getByLabelText("Tipo"), "Ausencia");

    expect(`${window.location.href}${window.location.search}${window.location.hash}`).not.toContain("secretoXYZ");
    expect(window.location.search).toBe("");
    expect(window.location.hash).toBe("");
    expect(JSON.stringify({ ...window.localStorage })).not.toContain("secretoXYZ");
    expect(JSON.stringify({ ...window.sessionStorage })).not.toContain("secretoXYZ");
    expect(window.localStorage).toHaveLength(0);
    expect(window.sessionStorage).toHaveLength(0);
  });
});

describe("the filter with the names masked", () => {
  it("still searches by name, and the names stay blurred", async () => {
    vi.stubEnv("NEXT_PUBLIC_MASK_NAMES", "true");
    const user = userEvent.setup();
    await renderQueue();

    await user.type(search(), "vídeo");

    expect(shownIds()).toEqual([2]);
    expect(screen.getByText("Vídeo")).toHaveStyle({ filter: "blur(6px)", userSelect: "none", pointerEvents: "none" });
  });
});
