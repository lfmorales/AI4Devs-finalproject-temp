import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ExceptionsPage from "@/app/(authenticated)/exceptions/page";
import type { IngestionException } from "@/lib/api/exceptions";
import { installRoutes, plain, renderAuthenticated, reply, type FakeReply } from "../../../helpers/api-pages";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

const OPEN = "GET /ingestion-exceptions?status=open";
const RESOLVED = "GET /ingestion-exceptions?status=resolved";
const RESOLVE_5 = "POST /ingestion-exceptions/5/resolve";

function exception(overrides: Partial<IngestionException> = {}): IngestionException {
  return {
    id: 5, exception_type: "unmatched_delivery", status: "open", ingestion_batch_id: 3, dsp_id: 1,
    external_campaign_id: "C-9", external_line_item_id: "L-9", campaign_line_id: null, campaign_period_id: null,
    first_date: "2026-08-03", last_date: "2026-08-08", days: 3, impressions_total: 40000, clicks_total: 11000,
    resolved_at: null, resolved_by: null, note: null, ...overrides,
  };
}

const RESOLVED_ROW = exception({ id: 6, status: "resolved", resolved_at: "2026-08-10T09:00:00", resolved_by: 2, note: "Typo en el id" });

async function openResolveDialog(user: ReturnType<typeof userEvent.setup>, id = 5) {
  await user.click(await screen.findByRole("button", { name: `Resolver excepción ${id}` }));
  return screen.getByRole("dialog", { name: `Resolver excepción ${id}` });
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe("the exception queue", () => {
  it("lists the open exceptions by default, with the tab «Abiertas» selected", async () => {
    const requests = installRoutes({ [OPEN]: () => reply(200, [exception()]) });

    renderAuthenticated(<ExceptionsPage />);

    await screen.findByRole("table", { name: "Cola de excepciones" });
    expect(screen.getByRole("tab", { name: "Abiertas" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Resueltas" })).toHaveAttribute("aria-selected", "false");
    expect(requests.map((r) => r.path)).toEqual(["/ingestion-exceptions?status=open"]);
  });

  it("shows type, DSP, external pair, dates, days, impressions and clicks, and never cost", async () => {
    installRoutes({ [OPEN]: () => reply(200, [exception()]) });

    renderAuthenticated(<ExceptionsPage />);

    const table = await screen.findByRole("table", { name: "Cola de excepciones" });
    const headers = within(table).getAllByRole("columnheader").map((h) => plain(h));
    for (const name of ["Tipo", "DSP", "Pareja externa", "Primera fecha", "Última fecha", "Días", "Impresiones", "Clics"]) {
      expect(headers).toContain(name);
    }
    expect(headers.some((name) => /cost/i.test(name))).toBe(false);
    const cells = within(within(table).getAllByRole("row")[1]!).getAllByRole("cell");
    const byHeader = (name: string) => plain(cells[headers.indexOf(name)]!);
    expect(byHeader("Tipo")).toBe("Entrega sin emparejar");
    expect(byHeader("DSP")).toBe("DSP 1");
    expect(byHeader("Pareja externa")).toBe("C-9 / L-9");
    expect(byHeader("Primera fecha")).toBe("2026-08-03");
    expect(byHeader("Última fecha")).toBe("2026-08-08");
    expect(byHeader("Días")).toBe("3");
    expect(byHeader("Impresiones")).toBe("40.000");
    expect(byHeader("Clics")).toBe("11.000");
  });

  it("lists the resolved exceptions, with their note, when «Resueltas» is chosen", async () => {
    const user = userEvent.setup();
    const requests = installRoutes({ [OPEN]: () => reply(200, [exception()]), [RESOLVED]: () => reply(200, [RESOLVED_ROW]) });
    renderAuthenticated(<ExceptionsPage />);
    await screen.findByRole("table", { name: "Cola de excepciones" });

    await user.click(screen.getByRole("tab", { name: "Resueltas" }));

    expect(await screen.findByText("Typo en el id")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Resueltas" })).toHaveAttribute("aria-selected", "true");
    expect(requests.at(-1)?.path).toBe("/ingestion-exceptions?status=resolved");
    expect(screen.queryByRole("button", { name: /^Resolver/ })).not.toBeInTheDocument();
  });

  it("shows the loading, the empty and the error states apart from each other", async () => {
    const user = userEvent.setup();
    installRoutes({
      [OPEN]: () => new Promise<FakeReply>(() => {}),
      [RESOLVED]: () => reply(200, []),
    });
    renderAuthenticated(<ExceptionsPage />);

    expect(await screen.findByText("Cargando excepciones…")).toBeInTheDocument();
    expect(screen.queryByText("No hay excepciones resueltas")).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Resueltas" }));
    expect(await screen.findByText("No hay excepciones resueltas")).toBeInTheDocument();
    expect(screen.queryByText("Cargando excepciones…")).not.toBeInTheDocument();
  });

  it("says the open queue is empty, and not loading, when nothing is open", async () => {
    installRoutes({ [OPEN]: () => reply(200, []) });

    renderAuthenticated(<ExceptionsPage />);

    expect(await screen.findByText("No hay excepciones abiertas")).toBeInTheDocument();
    expect(screen.queryByText("Cargando excepciones…")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows an error, and not an empty queue, when the list fails to load", async () => {
    installRoutes({ [OPEN]: () => reply(500, { code: "internal_error", message: "x" }) });

    renderAuthenticated(<ExceptionsPage />);

    expect(await screen.findByText("No se pudo cargar la cola de excepciones. Inténtalo de nuevo más tarde.")).toBeInTheDocument();
    expect(screen.queryByText("No hay excepciones abiertas")).not.toBeInTheDocument();
  });

  it("shows the session-expired page on a 401", async () => {
    installRoutes({ [OPEN]: () => reply(401, { code: "invalid_token", message: "x" }) });

    renderAuthenticated(<ExceptionsPage />);

    await waitFor(() => expect(screen.getByText("Sesión caducada")).toBeInTheDocument());
  });

  it("shows the access-denied page to a user without the operations role", async () => {
    installRoutes({ [OPEN]: () => reply(403, { code: "missing_role", message: "x" }) });

    renderAuthenticated(<ExceptionsPage />);

    await waitFor(() => expect(screen.getByText("Acceso denegado")).toBeInTheDocument());
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Abiertas" })).not.toBeInTheDocument();
  });
});

describe("resolving an exception", () => {
  it("asks for an optional note and sends nothing until confirmed", async () => {
    const user = userEvent.setup();
    const requests = installRoutes({ [OPEN]: () => reply(200, [exception()]) });
    renderAuthenticated(<ExceptionsPage />);

    const dialog = await openResolveDialog(user);

    expect(within(dialog).getByLabelText("Nota (opcional)")).toBeInTheDocument();
    expect(requests.filter((r) => r.method === "POST")).toEqual([]);
  });

  it("sends the note, removes the row from «Abiertas» and does not reload the list", async () => {
    const user = userEvent.setup();
    const requests = installRoutes({
      [OPEN]: () => reply(200, [exception(), exception({ id: 7 })]),
      [RESOLVE_5]: () => reply(200, exception({ status: "resolved", note: "Typo" })),
    });
    renderAuthenticated(<ExceptionsPage />);
    const dialog = await openResolveDialog(user);

    await user.type(within(dialog).getByLabelText("Nota (opcional)"), "Typo");
    await user.click(within(dialog).getByRole("button", { name: "Confirmar resolución" }));

    await waitFor(() => expect(screen.queryByRole("button", { name: "Resolver excepción 5" })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Resolver excepción 7" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Excepción 5 resuelta.");
    expect(requests.find((r) => r.method === "POST")?.body).toEqual({ note: "Typo" });
    expect(requests.filter((r) => r.path === "/ingestion-exceptions?status=open")).toHaveLength(1);
  });

  it("sends a null note when none was typed", async () => {
    const user = userEvent.setup();
    const requests = installRoutes({
      [OPEN]: () => reply(200, [exception()]), [RESOLVE_5]: () => reply(200, exception({ status: "resolved" })),
    });
    renderAuthenticated(<ExceptionsPage />);
    const dialog = await openResolveDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirmar resolución" }));

    await waitFor(() => expect(requests.find((r) => r.method === "POST")).toBeDefined());
    expect(requests.find((r) => r.method === "POST")?.body).toEqual({ note: null });
  });

  it("sends nothing and keeps the row when the dialog is cancelled", async () => {
    const user = userEvent.setup();
    const requests = installRoutes({ [OPEN]: () => reply(200, [exception()]) });
    renderAuthenticated(<ExceptionsPage />);
    const dialog = await openResolveDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resolver excepción 5" })).toBeInTheDocument();
    expect(requests.filter((r) => r.method === "POST")).toEqual([]);
  });

  it("says in Spanish that it was already resolved on a 409, and takes the row out of the open queue", async () => {
    const user = userEvent.setup();
    installRoutes({
      [OPEN]: () => reply(200, [exception()]),
      [RESOLVE_5]: () => reply(409, { code: "exception_already_resolved", message: "The exception is already resolved" }),
    });
    renderAuthenticated(<ExceptionsPage />);
    const dialog = await openResolveDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirmar resolución" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Esta excepción ya estaba resuelta.");
    expect(screen.queryByText(/already resolved/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Resolver excepción 5" })).not.toBeInTheDocument();
  });

  it("says in Spanish that it no longer exists on a 404, and takes the row out of the open queue", async () => {
    const user = userEvent.setup();
    installRoutes({
      [OPEN]: () => reply(200, [exception()]),
      [RESOLVE_5]: () => reply(404, { code: "exception_not_found", message: "The exception does not exist" }),
    });
    renderAuthenticated(<ExceptionsPage />);
    const dialog = await openResolveDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirmar resolución" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("La excepción ya no existe.");
    expect(screen.queryByText(/does not exist/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Resolver excepción 5" })).not.toBeInTheDocument();
  });

  it("keeps the row and shows a generic Spanish error on any other failure", async () => {
    const user = userEvent.setup();
    installRoutes({
      [OPEN]: () => reply(200, [exception()]), [RESOLVE_5]: () => reply(500, { code: "internal_error", message: "boom" }),
    });
    renderAuthenticated(<ExceptionsPage />);
    const dialog = await openResolveDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirmar resolución" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo resolver la excepción. Inténtalo de nuevo.");
    expect(screen.getByRole("button", { name: "Resolver excepción 5" })).toBeInTheDocument();
  });

  it("shows the session-expired page when the resolution gets a 401", async () => {
    const user = userEvent.setup();
    installRoutes({
      [OPEN]: () => reply(200, [exception()]), [RESOLVE_5]: () => reply(401, { code: "invalid_token", message: "x" }),
    });
    renderAuthenticated(<ExceptionsPage />);
    const dialog = await openResolveDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirmar resolución" }));

    await waitFor(() => expect(screen.getByText("Sesión caducada")).toBeInTheDocument());
  });

  it("shows the access-denied page when the resolution gets a 403", async () => {
    const user = userEvent.setup();
    installRoutes({
      [OPEN]: () => reply(200, [exception()]), [RESOLVE_5]: () => reply(403, { code: "missing_role", message: "x" }),
    });
    renderAuthenticated(<ExceptionsPage />);
    const dialog = await openResolveDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirmar resolución" }));

    await waitFor(() => expect(screen.getByText("Acceso denegado")).toBeInTheDocument());
  });
});
