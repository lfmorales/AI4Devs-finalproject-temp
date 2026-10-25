import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import DspCatalogPage from "@/app/(authenticated)/dsp-catalog/page";
import type { DspCatalogItem } from "@/lib/api/dsp-catalog";
import { installRoutes, plain, renderAuthenticated, reply } from "../../../helpers/api-pages";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

const FIRST_PAGE = "GET /dsp-catalog?limit=50&offset=0";
const UNLINK_7 = "DELETE /campaign-lines/7/dsp-mappings";
const BUTTON = "Desvincular: Navidad 2026 / Display ES";

function item(overrides: Partial<DspCatalogItem> = {}): DspCatalogItem {
  return {
    dsp_id: 1, external_campaign_id: "C-1", external_line_item_id: "L-1", campaign_name: "Navidad 2026", line_item_name: "Display ES",
    line_start_date: "2026-12-01", line_end_date: "2026-12-31", first_seen_date: "2026-12-01", last_seen_date: "2026-12-20",
    last_impressions_date: "2026-12-19", mapped_line_id: 7, ...overrides,
  };
}

const page = (items: DspCatalogItem[]) => reply(200, { items, total: items.length, limit: 50, offset: 0 });

async function askToUnlink(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: BUTTON }));
  return screen.getByRole("dialog", { name: "Desvincular la pareja" });
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe("unlinking a pair from the catalogue", () => {
  it("offers «Desvincular» on linked rows only", async () => {
    installRoutes({ [FIRST_PAGE]: () => page([item(), item({ line_item_name: "Video", mapped_line_id: null })]) });

    renderAuthenticated(<DspCatalogPage />);

    expect(await screen.findByRole("button", { name: BUTTON })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Desvincular: Navidad 2026 / Video" })).not.toBeInTheDocument();
  });

  it("asks for confirmation, saying the ingested delivery days will be deleted, and sends nothing yet", async () => {
    const user = userEvent.setup();
    const requests = installRoutes({ [FIRST_PAGE]: () => page([item()]) });
    renderAuthenticated(<DspCatalogPage />);

    const dialog = await askToUnlink(user);

    expect(plain(dialog)).toContain("Se borrarán los días de entrega ingeridos de la línea vinculada a Navidad 2026 / Display ES");
    expect(requests.filter((r) => r.method === "DELETE")).toEqual([]);
    expect(document.body).not.toHaveTextContent("C-1");
  });

  it("sends nothing when the confirmation is cancelled", async () => {
    const user = userEvent.setup();
    const requests = installRoutes({ [FIRST_PAGE]: () => page([item()]) });
    renderAuthenticated(<DspCatalogPage />);
    const dialog = await askToUnlink(user);

    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(requests.filter((r) => r.method === "DELETE")).toEqual([]);
    expect(screen.getByRole("button", { name: BUTTON })).toBeInTheDocument();
  });

  it.each([[12, "Pareja desvinculada. Se retiraron 12 días de entrega."], [1, "Pareja desvinculada. Se retiró 1 día de entrega."], [0, "Pareja desvinculada. No había días de entrega que retirar."]])(
    "after confirming, shows how many days were removed (%i)", async (days, message) => {
      const user = userEvent.setup();
      const requests = installRoutes({
        [FIRST_PAGE]: () => page([item()]),
        [UNLINK_7]: () => reply(200, { campaign_line_id: 7, removed_delivery_days: days }),
      });
      renderAuthenticated(<DspCatalogPage />);
      const dialog = await askToUnlink(user);

      await user.click(within(dialog).getByRole("button", { name: "Confirmar desvinculación" }));

      expect(await screen.findByText(message)).toBeInTheDocument();
      expect(requests.filter((r) => r.method === "DELETE")).toHaveLength(1);
      expect(requests.filter((r) => r.path.startsWith("/dsp-catalog"))).toHaveLength(1);
    },
  );

  it("turns the row into an unlinked one that can be linked again", async () => {
    const user = userEvent.setup();
    installRoutes({
      [FIRST_PAGE]: () => page([item()]),
      [UNLINK_7]: () => reply(200, { campaign_line_id: 7, removed_delivery_days: 3 }),
    });
    renderAuthenticated(<DspCatalogPage />);
    const dialog = await askToUnlink(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirmar desvinculación" }));

    await screen.findByText(/Pareja desvinculada/);
    expect(screen.queryByRole("button", { name: BUTTON })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Vincular a una línea: Navidad 2026 / Display ES" })).toBeInTheDocument();
    const row = within(screen.getByRole("table", { name: "Catálogo Adform" })).getAllByRole("row")[1]!;
    expect(plain(within(row).getAllByRole("cell")[4]!)).toBe("No");
  });

  it.each([
    [409, "ambiguous_mapping", "Esta línea tiene varias vinculaciones y no se puede desvincular desde aquí.", true],
    [404, "mapping_not_found", "La línea ya no tiene ninguna vinculación.", false],
    [404, "line_not_found", "La línea ya no existe.", true],
  ])("shows %i %s in Spanish inside the dialog", async (status, code, message, stillLinked) => {
    const user = userEvent.setup();
    installRoutes({
      [FIRST_PAGE]: () => page([item()]),
      [UNLINK_7]: () => reply(status, { code, message: "Backend text in English" }),
    });
    renderAuthenticated(<DspCatalogPage />);
    const dialog = await askToUnlink(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirmar desvinculación" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(message);
    expect(screen.queryByText(/Backend text/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: BUTTON }) !== null).toBe(stillLinked);
  });

  it("shows a generic Spanish message on any other failure and keeps the row linked", async () => {
    const user = userEvent.setup();
    installRoutes({ [FIRST_PAGE]: () => page([item()]), [UNLINK_7]: () => reply(500, { code: "internal_error", message: "boom" }) });
    renderAuthenticated(<DspCatalogPage />);
    const dialog = await askToUnlink(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirmar desvinculación" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("No se pudo desvincular la pareja. Inténtalo de nuevo.");
    expect(screen.getByRole("button", { name: BUTTON })).toBeInTheDocument();
  });

  it.each([[401, "Sesión caducada"], [403, "Acceso denegado"]])("shows the matching page when the unlink gets a %i", async (status, text) => {
    const user = userEvent.setup();
    installRoutes({ [FIRST_PAGE]: () => page([item()]), [UNLINK_7]: () => reply(status, { code: "x", message: "x" }) });
    renderAuthenticated(<DspCatalogPage />);
    const dialog = await askToUnlink(user);

    await user.click(within(dialog).getByRole("button", { name: "Confirmar desvinculación" }));

    await waitFor(() => expect(screen.getByText(text)).toBeInTheDocument());
  });
});
