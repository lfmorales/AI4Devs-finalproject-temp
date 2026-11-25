import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import DspCatalogPage from "@/app/(authenticated)/dsp-catalog/page";
import type { DspCatalogItem, DspCatalogPage as Page, DspMapping, UnmappedLine } from "@/lib/api/dsp-catalog";
import { installRoutes, renderAuthenticated, reply, type Route } from "../../../helpers/api-pages";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ access_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

const EQUATIV_DSP = 3;
const FIRST_PAGE = "GET /dsp-catalog?limit=50&offset=0";
const UNMAPPED = "GET /campaign-lines/unmapped";
const PACKAGES = `GET /dsp-catalog?dsp_id=${EQUATIV_DSP}&mapped=false&limit=50`;
const MAP_12 = "POST /campaign-lines/12/dsp-mappings";

const ADFORM_LINE: UnmappedLine = {
  id: 4, campaign_name: "Campaña Navidad", line_number: 1, start_date: "2026-12-01", end_date: "2026-12-31", dsp_id: 1,
  dsp_name: "Adform",
};
const EQUATIV_LINE: UnmappedLine = {
  id: 12, campaign_name: "Campaña Deal", line_number: 2, start_date: "2026-11-01", end_date: "2026-11-30",
  dsp_id: EQUATIV_DSP, dsp_name: "Equativ",
};

function emptyPage(items: DspCatalogItem[] = []): Page {
  return { items, total: items.length, limit: 50, offset: 0 };
}

function equativPackage(id: string, name: string): DspCatalogItem {
  return {
    dsp_id: EQUATIV_DSP, external_campaign_id: id, external_line_item_id: id, campaign_name: name, line_item_name: name,
    line_start_date: null, line_end_date: null, first_seen_date: "2026-11-01", last_seen_date: "2026-11-23",
    last_impressions_date: "2026-11-23", mapped_line_id: null,
  };
}

function mapping(packageId: string, overrides: Partial<DspMapping> = {}): DspMapping {
  return {
    id: 30, campaign_line_id: 12, dsp_id: EQUATIV_DSP, external_campaign_id: packageId, external_line_item_id: packageId,
    validated_at: "2026-11-24T09:00:00", validation: "user_validated", last_impressions_date: "2026-11-23",
    needs_history_load: false, ...overrides,
  };
}

function routes(extra: Record<string, Route> = {}): Record<string, Route> {
  return {
    [FIRST_PAGE]: () => reply(200, emptyPage()),
    [UNMAPPED]: () => reply(200, [ADFORM_LINE, EQUATIV_LINE]),
    [PACKAGES]: () => reply(200, emptyPage([
      equativPackage("900000001", "Synthetic Package One"),
      equativPackage("900000002", "Synthetic Package Two"),
    ])),
    ...extra,
  };
}

async function openForTheEquativLine(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Vincular una línea de Equativ" }));
  const dialog = await screen.findByRole("dialog", { name: "Vincular una línea de Equativ" });
  await user.click(await within(dialog).findByRole("radio", { name: /Campaña Deal, línea 2/ }));
  return dialog;
}

const PACKAGE_FIELD = "Paquete de Equativ (auctionPackageDealId)";

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe("mapping a line on Equativ by writing its package", () => {
  it("asks for nothing more until the dialog is opened", async () => {
    const requests = installRoutes(routes());

    renderAuthenticated(<DspCatalogPage />);

    await screen.findByRole("button", { name: "Vincular una línea de Equativ" });
    expect(requests.map((r) => r.path)).toEqual(["/dsp-catalog?limit=50&offset=0"]);
  });

  it("lists only the lines on Equativ that have no mapping", async () => {
    const user = userEvent.setup();
    installRoutes(routes());
    renderAuthenticated(<DspCatalogPage />);

    await user.click(await screen.findByRole("button", { name: "Vincular una línea de Equativ" }));
    const dialog = await screen.findByRole("dialog", { name: "Vincular una línea de Equativ" });

    expect(await within(dialog).findByRole("radio", { name: /Campaña Deal, línea 2/ })).toBeInTheDocument();
    expect(within(dialog).queryByRole("radio", { name: /Campaña Navidad/ })).not.toBeInTheDocument();
  });

  it("sends the package written as both identifiers and says the mapping is validated by the user", async () => {
    const user = userEvent.setup();
    const requests = installRoutes(routes({ [MAP_12]: () => reply(201, mapping("900000001")) }));
    renderAuthenticated(<DspCatalogPage />);
    const dialog = await openForTheEquativLine(user);

    await user.type(within(dialog).getByRole("textbox", { name: PACKAGE_FIELD }), "900000001");
    await user.click(within(dialog).getByRole("button", { name: "Vincular paquete" }));

    const post = requests.find((r) => r.method === "POST");
    expect(post?.path).toBe("/campaign-lines/12/dsp-mappings");
    expect(post?.body).toEqual({ external_campaign_id: "900000001", external_line_item_id: "900000001" });
    const notice = await screen.findByRole("status");
    expect(notice).toHaveTextContent("Paquete 900000001 vinculado a Campaña Deal, línea 2.");
    expect(notice).toHaveTextContent("Validado por el usuario: no se consulta a Equativ al vincular.");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("suggests the Equativ packages of the catalogue by name and id, and a suggestion fills the field", async () => {
    const user = userEvent.setup();
    installRoutes(routes());
    renderAuthenticated(<DspCatalogPage />);
    const dialog = await openForTheEquativLine(user);

    const suggestions = await within(dialog).findByRole("list", { name: "Paquetes del catálogo de Equativ" });
    expect(within(suggestions).getByRole("button", { name: "900000001 · Synthetic Package One" })).toBeInTheDocument();
    await user.type(within(dialog).getByRole("textbox", { name: PACKAGE_FIELD }), "Two");
    expect(within(suggestions).queryByRole("button", { name: /Synthetic Package One/ })).not.toBeInTheDocument();
    await user.click(within(suggestions).getByRole("button", { name: "900000002 · Synthetic Package Two" }));

    expect(within(dialog).getByRole("textbox", { name: PACKAGE_FIELD })).toHaveValue("900000002");
  });

  it("accepts a package that is not suggested", async () => {
    const user = userEvent.setup();
    const requests = installRoutes(routes({ [MAP_12]: () => reply(201, mapping("900000123", { last_impressions_date: null })) }));
    renderAuthenticated(<DspCatalogPage />);
    const dialog = await openForTheEquativLine(user);

    await user.type(within(dialog).getByRole("textbox", { name: PACKAGE_FIELD }), "900000123");
    await user.click(within(dialog).getByRole("button", { name: "Vincular paquete" }));

    expect(requests.find((r) => r.method === "POST")?.body).toEqual({
      external_campaign_id: "900000123", external_line_item_id: "900000123",
    });
    expect(await screen.findByRole("status")).toHaveTextContent("No consta entrega reciente de este paquete");
  });

  it("shows invalid_equativ_package in Spanish beside the field and keeps the dialog open", async () => {
    const user = userEvent.setup();
    installRoutes(routes({
      [MAP_12]: () => reply(422, {
        code: "invalid_equativ_package",
        message: "An Equativ line is mapped by one auction package id, a whole number above zero with no leading zero, in both identifiers",
      }),
    }));
    renderAuthenticated(<DspCatalogPage />);
    const dialog = await openForTheEquativLine(user);

    const field = within(dialog).getByRole("textbox", { name: PACKAGE_FIELD });
    await user.type(field, "0900000001");
    await user.click(within(dialog).getByRole("button", { name: "Vincular paquete" }));

    const problem = await within(dialog).findByRole("alert");
    const spanish =
      "El identificador del paquete son solo cifras, sin ceros a la izquierda y mayor que cero, por ejemplo 900000001.";
    expect(problem).toHaveTextContent(spanish);
    expect(field).toHaveAccessibleDescription(spanish);
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(dialog).not.toHaveTextContent("auction package id");
  });

  it("no longer lists the line once it is mapped", async () => {
    const user = userEvent.setup();
    let mapped = false;
    installRoutes(routes({
      [UNMAPPED]: () => reply(200, mapped ? [ADFORM_LINE] : [ADFORM_LINE, EQUATIV_LINE]),
      [MAP_12]: () => { mapped = true; return reply(201, mapping("900000001")); },
    }));
    renderAuthenticated(<DspCatalogPage />);
    const dialog = await openForTheEquativLine(user);
    await user.type(within(dialog).getByRole("textbox", { name: PACKAGE_FIELD }), "900000001");
    await user.click(within(dialog).getByRole("button", { name: "Vincular paquete" }));
    await screen.findByRole("status");

    await user.click(screen.getByRole("button", { name: "Vincular una línea de Equativ" }));
    const reopened = await screen.findByRole("dialog", { name: "Vincular una línea de Equativ" });

    expect(await within(reopened).findByText("No hay líneas de Equativ sin vincular")).toBeInTheDocument();
  });
});
