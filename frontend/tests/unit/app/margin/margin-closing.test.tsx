import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import MarginPage from "@/app/(authenticated)/margin/page";
import { installRoutes, renderAuthenticated, reply, type FakeReply } from "../../../helpers/api-pages";
import { campaign, flight, line, margin } from "../../../helpers/margin-data";
import type { FlightState } from "@/lib/api/margin";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

/** A margin whose only flight is in the given state. */
function marginWith(...states: FlightState[]) {
  return margin({ campaigns: [campaign({ lines: [line({ flights: states.map((state, index) => flight({ flight_id: index + 1, state })) })] })] });
}

const GET_ALL = () => reply(200, marginWith("pending_close"));

/** The routes of a page showing August 2026, with the closing answering as given. */
function routes(closing: () => FakeReply | Promise<FakeReply>) {
  return {
    "GET /margin": GET_ALL,
    "GET /margin?year=2026&month=8": GET_ALL,
    "POST /margin/closings": closing,
  };
}

async function chooseAugust(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole("region", { name: "Totales del periodo" });
  await user.type(screen.getByLabelText("Año"), "2026");
  await user.selectOptions(screen.getByLabelText("Mes"), "agosto");
}

async function openDialog(user: ReturnType<typeof userEvent.setup>) {
  await chooseAugust(user);
  await user.click(screen.getByRole("button", { name: "Cerrar mes" }));
  return screen.getByRole("dialog");
}

describe("the close-month button", () => {
  it("is off until a year and a month are chosen, and says why", async () => {
    installRoutes(routes(() => reply(200, { year: 2026, month: 8, closed: 0, already_closed: 0 })));
    const user = userEvent.setup();

    renderAuthenticated(<MarginPage />);
    await screen.findByRole("region", { name: "Totales del periodo" });
    const button = screen.getByRole("button", { name: "Cerrar mes" });

    expect(button).toBeDisabled();
    expect(screen.getByText("Elige año y mes para cerrar un mes")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Año"), "2026");
    expect(button).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Mes"), "agosto");
    await waitFor(() => expect(button).toBeEnabled());
  });

  it("opens the shared native dialog that explains that closing freezes the rates and cannot be undone", async () => {
    const requests = installRoutes(routes(() => reply(200, { year: 2026, month: 8, closed: 3, already_closed: 0 })));
    const user = userEvent.setup();

    renderAuthenticated(<MarginPage />);
    const dialog = await openDialog(user);

    expect(dialog.tagName).toBe("DIALOG");
    expect(dialog).toHaveAccessibleName("Cerrar agosto de 2026");
    expect(within(dialog).getByText(/congela las tasas/)).toBeInTheDocument();
    expect(within(dialog).getByText(/no se puede deshacer/)).toBeInTheDocument();
    expect(within(dialog).getByText(/de todas las campañas del mes/)).toBeInTheDocument();
    expect(requests.some((request) => request.method === "POST")).toBe(false);
  });

  it("sends nothing when the dialog is cancelled, and closes it", async () => {
    const requests = installRoutes(routes(() => reply(200, { year: 2026, month: 8, closed: 3, already_closed: 0 })));
    const user = userEvent.setup();

    renderAuthenticated(<MarginPage />);
    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(requests.some((request) => request.method === "POST")).toBe(false);
  });

  it("closes the month on confirmation, tells how many flights were closed and reads the margin again", async () => {
    const requests = installRoutes(routes(() => reply(200, { year: 2026, month: 8, closed: 3, already_closed: 0 })));
    const user = userEvent.setup();

    renderAuthenticated(<MarginPage />);
    const dialog = await openDialog(user);
    const readsBefore = requests.filter((request) => request.method === "GET").length;
    await user.click(within(dialog).getByRole("button", { name: "Confirmar cierre" }));

    expect(await screen.findByText("Se cerraron 3 flights de agosto de 2026")).toBeInTheDocument();
    expect(requests.filter((request) => request.method === "POST")).toEqual([
      { method: "POST", path: "/margin/closings", body: { year: 2026, month: 8 } },
    ]);
    await waitFor(() => expect(requests.filter((request) => request.method === "GET").length).toBeGreaterThan(readsBefore));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("says 'Se cerró 1 flight' for a single flight", async () => {
    installRoutes(routes(() => reply(200, { year: 2026, month: 8, closed: 1, already_closed: 0 })));
    const user = userEvent.setup();

    renderAuthenticated(<MarginPage />);
    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole("button", { name: "Confirmar cierre" }));

    expect(await screen.findByText("Se cerró 1 flight de agosto de 2026")).toBeInTheDocument();
  });

  it("says that there are no ended flights when none was closed", async () => {
    installRoutes(routes(() => reply(200, { year: 2026, month: 8, closed: 0, already_closed: 0 })));
    const user = userEvent.setup();

    renderAuthenticated(<MarginPage />);
    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole("button", { name: "Confirmar cierre" }));

    expect(await screen.findByText("No hay flights terminados en este mes")).toBeInTheDocument();
    expect(screen.queryByText(/Se cerr/)).not.toBeInTheDocument();
  });

  it("mentions the flights that were already closed", async () => {
    installRoutes(routes(() => reply(200, { year: 2026, month: 8, closed: 0, already_closed: 4 })));
    const user = userEvent.setup();

    renderAuthenticated(<MarginPage />);
    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole("button", { name: "Confirmar cierre" }));

    expect(await screen.findByText("No hay flights terminados en este mes")).toBeInTheDocument();
    expect(screen.getByText("Ya estaban cerrados: 4")).toBeInTheDocument();
  });

  it("cannot be confirmed twice while the request is in flight", async () => {
    let answer: (reply: FakeReply) => void = () => {};
    const requests = installRoutes(routes(() => new Promise<FakeReply>((resolve) => { answer = resolve; })));
    const user = userEvent.setup();

    renderAuthenticated(<MarginPage />);
    const dialog = await openDialog(user);
    const confirm = within(dialog).getByRole("button", { name: "Confirmar cierre" });
    await user.click(confirm);

    await waitFor(() => expect(confirm).toBeDisabled());
    expect(within(dialog).getByRole("button", { name: "Cancelar" })).toBeDisabled();
    await user.click(confirm);
    expect(requests.filter((request) => request.method === "POST")).toHaveLength(1);
    answer(reply(200, { year: 2026, month: 8, closed: 2, already_closed: 0 }));
    expect(await screen.findByText("Se cerraron 2 flights de agosto de 2026")).toBeInTheDocument();
  });
});

describe("the availability of the close-month button", () => {
  const HELP = "No hay flights pendientes de cierre en este mes";

  async function showAugust(margins: FlightState[][], closing: () => FakeReply = () => reply(200, { year: 2026, month: 8, closed: 1, already_closed: 0 })) {
    let reads = 0;
    const answer = () => reply(200, marginWith(...(margins[Math.min(reads++, margins.length - 1)] ?? [])));
    installRoutes({ "GET /margin": () => reply(200, marginWith("pending_close")), "GET /margin?year=2026&month=8": answer, "POST /margin/closings": closing });
    const user = userEvent.setup();
    renderAuthenticated(<MarginPage />);
    await screen.findByRole("region", { name: "Totales del periodo" });
    await user.type(screen.getByLabelText("Año"), "2026");
    await user.selectOptions(screen.getByLabelText("Mes"), "agosto");
    return user;
  }

  it("is off, with an accessible help text, for a month with only closed flights", async () => {
    await showAugust([["closed", "closed"]]);

    const button = screen.getByRole("button", { name: "Cerrar mes" });
    await waitFor(() => expect(button).toBeDisabled());
    expect(button).toHaveAccessibleDescription(HELP);
  });

  it("is off for a month with only running flights", async () => {
    await showAugust([["running"]]);

    const button = screen.getByRole("button", { name: "Cerrar mes" });
    await waitFor(() => expect(button).toBeDisabled());
    expect(button).toHaveAccessibleDescription(HELP);
  });

  it("is on, without the help text, as soon as one flight is pending close among others", async () => {
    await showAugust([["closed", "running", "pending_close"]]);

    const button = screen.getByRole("button", { name: "Cerrar mes" });
    await waitFor(() => expect(button).toBeEnabled());
    expect(screen.queryByText(HELP)).not.toBeInTheDocument();
  });

  it("is off again after closing the month and reloading", async () => {
    const user = await showAugust([["pending_close"], ["closed"]]);
    const button = screen.getByRole("button", { name: "Cerrar mes" });
    await waitFor(() => expect(button).toBeEnabled());

    await user.click(button);
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Confirmar cierre" }));

    expect(await screen.findByText("Se cerró 1 flight de agosto de 2026")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Cerrar mes" })).toBeDisabled());
    expect(screen.getByRole("button", { name: "Cerrar mes" })).toHaveAccessibleDescription(HELP);
  });

  const REMOVE_FILTER = "Quita el filtro de campaña para cerrar el mes";

  it("is off in any month while a campaign filter is active, and does not change when the month changes", async () => {
    installRoutes({
      "GET /margin": () => reply(200, marginWith("pending_close")),
      "GET /margin?year=2026&month=8": () => reply(200, marginWith("pending_close")),
      "GET /margin?year=2026&month=8&campaign_id=1": () => reply(200, marginWith("pending_close")),
      "GET /margin?year=2026&month=9&campaign_id=1": () => reply(200, marginWith("pending_close")),
    });
    const user = userEvent.setup();
    renderAuthenticated(<MarginPage />);
    await screen.findByRole("region", { name: "Totales del periodo" });
    await user.type(screen.getByLabelText("Año"), "2026");
    await user.selectOptions(screen.getByLabelText("Mes"), "agosto");
    await waitFor(() => expect(screen.getByRole("button", { name: "Cerrar mes" })).toBeEnabled());

    await user.selectOptions(screen.getByLabelText("Campaña"), "Campaña A");

    const button = screen.getByRole("button", { name: "Cerrar mes" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription(REMOVE_FILTER);
    await user.selectOptions(screen.getByLabelText("Mes"), "septiembre");
    await screen.findByRole("region", { name: "Totales del periodo" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription(REMOVE_FILTER);
    expect(screen.queryByText(HELP)).not.toBeInTheDocument();
  });

  it("is off under a campaign filter even before a month is chosen", async () => {
    installRoutes({ "GET /margin": () => reply(200, marginWith("pending_close")), "GET /margin?campaign_id=1": () => reply(200, marginWith("pending_close")) });
    const user = userEvent.setup();
    renderAuthenticated(<MarginPage />);
    await screen.findByRole("region", { name: "Totales del periodo" });

    await user.selectOptions(screen.getByLabelText("Campaña"), "Campaña A");

    expect(screen.getByRole("button", { name: "Cerrar mes" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cerrar mes" })).toHaveAccessibleDescription(REMOVE_FILTER);
  });

  it("decides again by the flights of the loaded month once the campaign filter is removed", async () => {
    installRoutes({
      "GET /margin": () => reply(200, marginWith("pending_close")),
      "GET /margin?year=2026&month=8": () => reply(200, marginWith("closed")),
      "GET /margin?year=2026&month=8&campaign_id=1": () => reply(200, marginWith("pending_close")),
    });
    const user = userEvent.setup();
    renderAuthenticated(<MarginPage />);
    await screen.findByRole("region", { name: "Totales del periodo" });
    await user.type(screen.getByLabelText("Año"), "2026");
    await user.selectOptions(screen.getByLabelText("Mes"), "agosto");
    await user.selectOptions(screen.getByLabelText("Campaña"), "Campaña A");
    expect(screen.getByRole("button", { name: "Cerrar mes" })).toHaveAccessibleDescription(REMOVE_FILTER);

    await user.selectOptions(screen.getByLabelText("Campaña"), "Todas");

    await waitFor(() => expect(screen.getByRole("button", { name: "Cerrar mes" })).toHaveAccessibleDescription(HELP));
    expect(screen.getByRole("button", { name: "Cerrar mes" })).toBeDisabled();
  });

  it("uses no data of another month when the month changes without a filter", async () => {
    let answerSeptember: (reply: FakeReply) => void = () => {};
    installRoutes({
      "GET /margin": () => reply(200, marginWith("closed")),
      "GET /margin?year=2026&month=8": () => reply(200, marginWith("pending_close")),
      "GET /margin?year=2026&month=9": () => new Promise<FakeReply>((resolve) => { answerSeptember = resolve; }),
    });
    const user = userEvent.setup();
    renderAuthenticated(<MarginPage />);
    await screen.findByRole("region", { name: "Totales del periodo" });
    await user.type(screen.getByLabelText("Año"), "2026");
    await user.selectOptions(screen.getByLabelText("Mes"), "agosto");
    await waitFor(() => expect(screen.getByRole("button", { name: "Cerrar mes" })).toBeEnabled());

    await user.selectOptions(screen.getByLabelText("Mes"), "septiembre");

    await waitFor(() => expect(screen.getByRole("button", { name: "Cerrar mes" })).toBeDisabled());
    answerSeptember(reply(200, marginWith("closed")));
    await screen.findByRole("region", { name: "Totales del periodo" });
    expect(screen.getByRole("button", { name: "Cerrar mes" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cerrar mes" })).toHaveAccessibleDescription(HELP);
  });

  it("keeps the year-and-month hint, not this one, while no month is chosen", async () => {
    installRoutes({ "GET /margin": () => reply(200, marginWith("closed")) });
    renderAuthenticated(<MarginPage />);
    await screen.findByRole("region", { name: "Totales del periodo" });

    expect(screen.getByRole("button", { name: "Cerrar mes" })).toHaveAccessibleDescription("Elige año y mes para cerrar un mes");
    expect(screen.queryByText(HELP)).not.toBeInTheDocument();
  });
});

describe("the errors of the closing", () => {
  async function failWith(status: number, code: string, message: string) {
    installRoutes(routes(() => reply(status, { code, message })));
    const user = userEvent.setup();
    renderAuthenticated(<MarginPage />);
    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole("button", { name: "Confirmar cierre" }));
    return (await screen.findByRole("alert")).textContent ?? "";
  }

  it("names the month that blocks the closing, in Spanish", async () => {
    const text = await failWith(409, "previous_month_open", "An earlier month is still open: 2026-06. Close it first.");

    expect(text).toBe("Hay un mes anterior sin cerrar: junio de 2026. Ciérralo antes de cerrar agosto de 2026.");
  });

  it("names whichever month the server names", async () => {
    const text = await failWith(409, "previous_month_open", "An earlier month is still open: 2026-01. Close it first.");

    expect(text).toContain("enero de 2026");
  });

  it("says something useful even if the month cannot be read from the message", async () => {
    const text = await failWith(409, "previous_month_open", "unreadable");

    expect(text).toBe("Hay un mes anterior sin cerrar. Ciérralo antes de cerrar agosto de 2026.");
  });

  it("answers every other code of the backend in Spanish, each with a message of its own", async () => {
    const codes: [number, string][] = [
      [422, "validation_error"],
      [404, "campaign_not_found"],
      [500, "platform_rate_not_configured"],
      [503, "identity_provider_unavailable"],
      [500, "internal_error"],
    ];
    const messages: string[] = [];
    for (const [status, code] of codes) {
      messages.push(await failWith(status, code, "english text of the backend"));
      document.body.innerHTML = "";
      vi.unstubAllGlobals();
    }

    expect(new Set(messages).size).toBe(codes.length);
    for (const message of messages) {
      expect(message).not.toContain("english text of the backend");
      expect(message).toMatch(/[áéíóúñ¿]|[A-Z][a-z]+ [a-z]+/);
    }
  });

  it("uses a generic message for a code it does not know, never the backend's own text", async () => {
    const text = await failWith(500, "something_new", "internal detail of the backend");

    expect(text).toBe("No se pudo cerrar el mes. Inténtalo de nuevo más tarde.");
  });

  it("leaves the dialog and offers the button again after an error", async () => {
    installRoutes(routes(() => reply(500, { code: "internal_error", message: "x" })));
    const user = userEvent.setup();

    renderAuthenticated(<MarginPage />);
    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole("button", { name: "Confirmar cierre" }));
    await screen.findByRole("alert");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cerrar mes" })).toBeEnabled();
  });
});
