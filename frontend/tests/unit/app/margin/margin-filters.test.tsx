import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import MarginPage from "@/app/(authenticated)/margin/page";
import { installRoutes, renderAuthenticated, reply } from "../../../helpers/api-pages";
import { campaign, margin } from "../../../helpers/margin-data";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

const TWO_CAMPAIGNS = margin({ campaigns: [campaign({ campaign_id: 7, name: "Alfa" }), campaign({ campaign_id: 9, name: "Beta" })] });
const ONLY_BETA = margin({ campaigns: [campaign({ campaign_id: 9, name: "Beta" })] });

beforeEach(() => vi.clearAllMocks());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

function paths(requests: { method: string; path: string }[]): string[] {
  return requests.filter((request) => request.method === "GET").map((request) => request.path);
}

describe("the filters of the margin page", () => {
  it("asks for the whole margin first", async () => {
    const requests = installRoutes({ "GET /margin": () => reply(200, TWO_CAMPAIGNS) });

    renderAuthenticated(<MarginPage />);
    await screen.findByRole("group", { name: "Campaña Alfa" });

    expect(paths(requests)).toEqual(["/margin"]);
  });

  it("asks again with the year when it is written", async () => {
    const requests = installRoutes({
      "GET /margin": () => reply(200, TWO_CAMPAIGNS),
      "GET /margin?year=2026": () => reply(200, TWO_CAMPAIGNS),
    });
    const user = userEvent.setup();

    renderAuthenticated(<MarginPage />);
    await screen.findByRole("group", { name: "Campaña Alfa" });
    await user.type(screen.getByLabelText("Año"), "2026");

    await waitFor(() => expect(paths(requests)).toContain("/margin?year=2026"));
  });

  it("asks with the month chosen by name, as a number", async () => {
    const requests = installRoutes({
      "GET /margin": () => reply(200, TWO_CAMPAIGNS),
      "GET /margin?month=8": () => reply(200, TWO_CAMPAIGNS),
    });
    const user = userEvent.setup();

    renderAuthenticated(<MarginPage />);
    await screen.findByRole("group", { name: "Campaña Alfa" });
    await user.selectOptions(screen.getByLabelText("Mes"), "agosto");

    await waitFor(() => expect(paths(requests)).toContain("/margin?month=8"));
  });

  it("lists the twelve months and 'Todos'", async () => {
    installRoutes({ "GET /margin": () => reply(200, TWO_CAMPAIGNS) });

    renderAuthenticated(<MarginPage />);
    await screen.findByRole("group", { name: "Campaña Alfa" });

    const options = Array.from((screen.getByLabelText("Mes") as HTMLSelectElement).options).map((option) => option.text);
    expect(options).toEqual(["Todos", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]);
  });

  it("offers the campaigns of the margin it loaded and asks by the id of the one chosen", async () => {
    const requests = installRoutes({
      "GET /margin": () => reply(200, TWO_CAMPAIGNS),
      "GET /margin?campaign_id=9": () => reply(200, ONLY_BETA),
    });
    const user = userEvent.setup();

    renderAuthenticated(<MarginPage />);
    await screen.findByRole("group", { name: "Campaña Alfa" });
    const select = screen.getByLabelText("Campaña") as HTMLSelectElement;
    expect(Array.from(select.options).map((option) => option.text)).toEqual(["Todas", "Alfa", "Beta"]);
    await user.selectOptions(select, "Beta");

    await waitFor(() => expect(paths(requests)).toContain("/margin?campaign_id=9"));
    await waitFor(() => expect(screen.queryByRole("group", { name: "Campaña Alfa" })).not.toBeInTheDocument());
    expect(screen.getByRole("group", { name: "Campaña Beta" })).toBeInTheDocument();
  });

  it("keeps offering every campaign after one is chosen, so that another can be picked", async () => {
    installRoutes({
      "GET /margin": () => reply(200, TWO_CAMPAIGNS),
      "GET /margin?campaign_id=9": () => reply(200, ONLY_BETA),
    });
    const user = userEvent.setup();

    renderAuthenticated(<MarginPage />);
    await screen.findByRole("group", { name: "Campaña Alfa" });
    await user.selectOptions(screen.getByLabelText("Campaña"), "Beta");
    await screen.findByRole("group", { name: "Campaña Beta" });

    const options = Array.from((screen.getByLabelText("Campaña") as HTMLSelectElement).options).map((option) => option.text);
    expect(options).toEqual(["Todas", "Alfa", "Beta"]);
  });

  it("combines the three filters in the query, in the order of the API", async () => {
    const requests = installRoutes({
      "GET /margin": () => reply(200, TWO_CAMPAIGNS),
      "GET /margin?year=2026": () => reply(200, TWO_CAMPAIGNS),
      "GET /margin?year=2026&month=8": () => reply(200, TWO_CAMPAIGNS),
      "GET /margin?year=2026&month=8&campaign_id=7": () => reply(200, margin({ campaigns: [campaign({ campaign_id: 7, name: "Alfa" })] })),
    });
    const user = userEvent.setup();

    renderAuthenticated(<MarginPage />);
    await screen.findByRole("group", { name: "Campaña Alfa" });
    await user.type(screen.getByLabelText("Año"), "2026");
    await user.selectOptions(screen.getByLabelText("Mes"), "agosto");
    await user.selectOptions(screen.getByLabelText("Campaña"), "Alfa");

    await waitFor(() => expect(paths(requests)).toContain("/margin?year=2026&month=8&campaign_id=7"));
  });

  it("clears the filters with a button, which is off while there is none", async () => {
    installRoutes({
      "GET /margin": () => reply(200, TWO_CAMPAIGNS),
      "GET /margin?month=8": () => reply(200, TWO_CAMPAIGNS),
    });
    const user = userEvent.setup();

    renderAuthenticated(<MarginPage />);
    await screen.findByRole("group", { name: "Campaña Alfa" });
    const clear = screen.getByRole("button", { name: "Limpiar filtros" });
    expect(clear).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Mes"), "agosto");
    await waitFor(() => expect(clear).toBeEnabled());
    await user.click(clear);

    await waitFor(() => expect((screen.getByLabelText("Mes") as HTMLSelectElement).value).toBe(""));
    expect(clear).toBeDisabled();
  });

  it("keeps what is chosen out of the address and out of the browser's storage", async () => {
    const before = window.location.href;
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    installRoutes({
      "GET /margin": () => reply(200, TWO_CAMPAIGNS),
      "GET /margin?year=2026": () => reply(200, TWO_CAMPAIGNS),
      "GET /margin?year=2026&month=8": () => reply(200, TWO_CAMPAIGNS),
    });
    const user = userEvent.setup();

    renderAuthenticated(<MarginPage />);
    await screen.findByRole("group", { name: "Campaña Alfa" });
    await user.type(screen.getByLabelText("Año"), "2026");
    await user.selectOptions(screen.getByLabelText("Mes"), "agosto");
    await waitFor(() => expect(screen.getByLabelText("Mes")).toHaveValue("8"));

    expect(window.location.href).toBe(before);
    expect(setItem).not.toHaveBeenCalled();
    setItem.mockRestore();
  });

  it("labels the campaigns by their id, not their name, when names are masked", async () => {
    vi.stubEnv("NEXT_PUBLIC_MASK_NAMES", "true");
    installRoutes({ "GET /margin": () => reply(200, TWO_CAMPAIGNS) });

    renderAuthenticated(<MarginPage />);
    await screen.findByRole("group", { name: "Campaña Alfa" });

    const options = Array.from((screen.getByLabelText("Campaña") as HTMLSelectElement).options).map((option) => option.text);
    expect(options).toEqual(["Todas", "Campaña 7", "Campaña 9"]);
  });
});
