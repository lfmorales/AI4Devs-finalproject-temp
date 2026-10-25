import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ExceptionsPage from "@/app/(authenticated)/exceptions/page";
import type { UnmappedLine } from "@/lib/api/dsp-catalog";
import type { IngestionException, LinkExceptionResponse } from "@/lib/api/exceptions";
import { installRoutes, plain, renderAuthenticated, reply } from "../../../helpers/api-pages";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

const OPEN = "GET /ingestion-exceptions?status=open";
const RESOLVED = "GET /ingestion-exceptions?status=resolved";
const UNMAPPED = "GET /campaign-lines/unmapped";
const LINK_5 = "POST /ingestion-exceptions/5/link";

const HISTORY_WARNING =
  "Esta línea empezó antes de la ventana de siete días. La entrega anterior no se carga sola: pide cargar el histórico con run_ingestion --from … --to …";

function exception(overrides: Partial<IngestionException> = {}): IngestionException {
  return {
    id: 5, exception_type: "unmatched_delivery", status: "open", ingestion_batch_id: 3, dsp_id: 1,
    external_campaign_id: "C-9", external_line_item_id: "L-9", campaign_line_id: null, campaign_period_id: null,
    first_date: "2026-08-03", last_date: "2026-08-08", days: 3, impressions_total: 40000, clicks_total: 11000,
    resolved_at: null, resolved_by: null, note: null, campaign_name: null, line_item_name: null, ...overrides,
  };
}

const LINES: UnmappedLine[] = [
  { id: 4, campaign_name: "Campaña Navidad", line_number: 1, start_date: "2026-12-01", end_date: "2026-12-31", dsp_id: 1, dsp_name: "Adform" },
  { id: 8, campaign_name: "Campaña Verano", line_number: 2, start_date: "2026-07-01", end_date: "2026-08-31", dsp_id: 1, dsp_name: "Adform" },
];

function linked(needsHistoryLoad: boolean): LinkExceptionResponse {
  return {
    mapping: { id: 9, campaign_line_id: 4, dsp_id: 1, external_campaign_id: "C-9", external_line_item_id: "L-9", validated_at: "2026-08-10T09:00:00" },
    exception: exception({ status: "resolved" }),
    needs_history_load: needsHistoryLoad,
  };
}

async function chooseLine(user: ReturnType<typeof userEvent.setup>, id = 5, lineName = /Navidad/) {
  await user.click(await screen.findByRole("button", { name: `Vincular a una línea (excepción ${id})` }));
  const dialog = await screen.findByRole("dialog", { name: `Vincular la excepción ${id} a una línea` });
  await user.click(await within(dialog).findByRole("radio", { name: lineName }));
  return dialog;
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe("linking an exception from the queue", () => {
  it("offers «Vincular a una línea» on open unmatched-delivery exceptions only", async () => {
    const user = userEvent.setup();
    installRoutes({
      [OPEN]: () => reply(200, [exception(), exception({ id: 6, exception_type: "missing_delivery", campaign_line_id: 1, campaign_period_id: 2 })]),
      [RESOLVED]: () => reply(200, [exception({ id: 7, status: "resolved" })]),
    });
    renderAuthenticated(<ExceptionsPage />);

    expect(await screen.findByRole("button", { name: "Vincular a una línea (excepción 5)" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Vincular a una línea (excepción 6)" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Resueltas" }));
    await screen.findByRole("table", { name: "Cola de excepciones" });
    expect(screen.queryByRole("button", { name: /Vincular/ })).not.toBeInTheDocument();
  });

  it("sends nothing until the line is confirmed", async () => {
    const user = userEvent.setup();
    const requests = installRoutes({ [OPEN]: () => reply(200, [exception()]), [UNMAPPED]: () => reply(200, LINES) });
    renderAuthenticated(<ExceptionsPage />);

    await chooseLine(user);

    expect(requests.filter((r) => r.method === "POST")).toEqual([]);
  });

  it("links the chosen line, takes the row out of «Abiertas» without reloading and says so", async () => {
    const user = userEvent.setup();
    const requests = installRoutes({
      [OPEN]: () => reply(200, [exception(), exception({ id: 7 })]),
      [UNMAPPED]: () => reply(200, LINES),
      [LINK_5]: () => reply(200, linked(false)),
    });
    renderAuthenticated(<ExceptionsPage />);
    const dialog = await chooseLine(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirmar vinculación" }));

    await waitFor(() => expect(screen.queryByRole("button", { name: "Vincular a una línea (excepción 5)" })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Vincular a una línea (excepción 7)" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Excepción 5 vinculada a Campaña Navidad, línea 1.");
    expect(requests.find((r) => r.method === "POST")?.body).toEqual({ campaign_line_id: 4 });
    expect(requests.filter((r) => r.path === "/ingestion-exceptions?status=open")).toHaveLength(1);
    expect(screen.queryByText(HISTORY_WARNING, { exact: false })).not.toBeInTheDocument();
  });

  it("shows a persistent history warning, with no action, when the line needs a history load", async () => {
    const user = userEvent.setup();
    installRoutes({
      [OPEN]: () => reply(200, [exception(), exception({ id: 7 })]),
      [UNMAPPED]: () => reply(200, LINES),
      [LINK_5]: () => reply(200, linked(true)),
    });
    renderAuthenticated(<ExceptionsPage />);
    const dialog = await chooseLine(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirmar vinculación" }));

    const warning = await screen.findByText(HISTORY_WARNING, { exact: false });
    expect(plain(warning)).toContain(HISTORY_WARNING);
    expect(warning.closest("[role=alert]")).not.toBeNull();
    expect(screen.queryByRole("button", { name: /histórico/i })).not.toBeInTheDocument();
    // It stays when the user goes on working.
    await user.click(screen.getByRole("button", { name: "Vincular a una línea (excepción 7)" }));
    expect(screen.getByText(HISTORY_WARNING, { exact: false })).toBeInTheDocument();
  });

  it.each([
    [409, "exception_already_resolved", "Esta excepción ya estaba resuelta.", true],
    [404, "exception_not_found", "La excepción ya no existe.", true],
    [409, "exception_not_linkable", "Solo se puede vincular una excepción de entrega sin emparejar.", false],
    [404, "line_not_found", "La línea elegida ya no existe.", false],
    [422, "line_dsp_mismatch", "La línea elegida usa un DSP distinto al de esta excepción.", false],
    [409, "mapping_pair_taken", "Esta pareja de identificadores ya está vinculada a una línea.", false],
  ])("shows %i %s in Spanish inside the dialog (row leaves the queue: %s)", async (status, code, message, leaves) => {
    const user = userEvent.setup();
    installRoutes({
      [OPEN]: () => reply(200, [exception()]),
      [UNMAPPED]: () => reply(200, LINES),
      [LINK_5]: () => reply(status, { code, message: "Backend text in English" }),
    });
    renderAuthenticated(<ExceptionsPage />);
    const dialog = await chooseLine(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirmar vinculación" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(message);
    expect(screen.queryByText(/Backend text/)).not.toBeInTheDocument();
    const stillThere = screen.queryByRole("button", { name: "Vincular a una línea (excepción 5)" }) !== null;
    expect(stillThere).toBe(!leaves);
  });

  it("shows a generic Spanish message in the dialog on any other failure, and keeps the row", async () => {
    const user = userEvent.setup();
    installRoutes({
      [OPEN]: () => reply(200, [exception()]),
      [UNMAPPED]: () => reply(200, LINES),
      [LINK_5]: () => reply(500, { code: "internal_error", message: "boom" }),
    });
    renderAuthenticated(<ExceptionsPage />);
    const dialog = await chooseLine(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirmar vinculación" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("No se pudo vincular la excepción. Inténtalo de nuevo.");
    expect(screen.getByRole("button", { name: "Vincular a una línea (excepción 5)" })).toBeInTheDocument();
  });

  it("closes the dialog and keeps the row when cancelled", async () => {
    const user = userEvent.setup();
    const requests = installRoutes({ [OPEN]: () => reply(200, [exception()]), [UNMAPPED]: () => reply(200, LINES) });
    renderAuthenticated(<ExceptionsPage />);
    const dialog = await chooseLine(user);

    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(requests.filter((r) => r.method === "POST")).toEqual([]);
  });

  it("shows the session-expired page when the link gets a 401", async () => {
    const user = userEvent.setup();
    installRoutes({
      [OPEN]: () => reply(200, [exception()]), [UNMAPPED]: () => reply(200, LINES),
      [LINK_5]: () => reply(401, { code: "invalid_token", message: "x" }),
    });
    renderAuthenticated(<ExceptionsPage />);
    const dialog = await chooseLine(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirmar vinculación" }));

    await waitFor(() => expect(screen.getByText("Sesión caducada")).toBeInTheDocument());
  });

  it("shows the access-denied page when the link gets a 403", async () => {
    const user = userEvent.setup();
    installRoutes({
      [OPEN]: () => reply(200, [exception()]), [UNMAPPED]: () => reply(200, LINES),
      [LINK_5]: () => reply(403, { code: "missing_role", message: "x" }),
    });
    renderAuthenticated(<ExceptionsPage />);
    const dialog = await chooseLine(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirmar vinculación" }));

    await waitFor(() => expect(screen.getByText("Acceso denegado")).toBeInTheDocument());
  });

  it("shows the access-denied page when the unmapped lines answer 403", async () => {
    const user = userEvent.setup();
    installRoutes({
      [OPEN]: () => reply(200, [exception()]), [UNMAPPED]: () => reply(403, { code: "missing_role", message: "x" }),
    });
    renderAuthenticated(<ExceptionsPage />);

    await user.click(await screen.findByRole("button", { name: "Vincular a una línea (excepción 5)" }));

    await waitFor(() => expect(screen.getByText("Acceso denegado")).toBeInTheDocument());
  });
});

describe("the names in the queue", () => {
  it("shows the campaign and line item names the catalogue holds, in labelled columns", async () => {
    installRoutes({ [OPEN]: () => reply(200, [exception({ campaign_name: "Navidad 2026", line_item_name: "Display ES" })]) });

    renderAuthenticated(<ExceptionsPage />);

    const table = await screen.findByRole("table", { name: "Cola de excepciones" });
    const headers = within(table).getAllByRole("columnheader").map((h) => plain(h));
    const cells = within(within(table).getAllByRole("row")[1]!).getAllByRole("cell");
    expect(plain(cells[headers.indexOf("Campaña Adform")]!)).toBe("Navidad 2026");
    expect(plain(cells[headers.indexOf("Línea Adform")]!)).toBe("Display ES");
  });

  it("says «Sin nombre en el catálogo» for a null name, each on its own", async () => {
    installRoutes({ [OPEN]: () => reply(200, [exception({ campaign_name: "Navidad 2026", line_item_name: null })]) });

    renderAuthenticated(<ExceptionsPage />);

    const table = await screen.findByRole("table", { name: "Cola de excepciones" });
    expect(within(table).getAllByText("Sin nombre en el catálogo")).toHaveLength(1);
    expect(within(table).getByText("Navidad 2026")).toBeInTheDocument();
  });
});
