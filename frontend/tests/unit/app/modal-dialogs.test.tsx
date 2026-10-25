import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";

import DspCatalogPage from "@/app/(authenticated)/dsp-catalog/page";
import ExceptionsPage from "@/app/(authenticated)/exceptions/page";
import { installRoutes, renderAuthenticated, reply } from "../../helpers/api-pages";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

const EXCEPTION = {
  id: 5, exception_type: "unmatched_delivery", status: "open", ingestion_batch_id: 3, dsp_id: 1,
  external_campaign_id: "C-9", external_line_item_id: "L-9", campaign_line_id: null, campaign_period_id: null,
  first_date: "2026-08-03", last_date: "2026-08-08", days: 3, impressions_total: 4, clicks_total: 1,
  resolved_at: null, resolved_by: null, note: null, campaign_name: null, line_item_name: null,
};
const ITEM = {
  dsp_id: 1, external_campaign_id: "C-1", external_line_item_id: "L-1", campaign_name: "Navidad", line_item_name: "Display",
  line_start_date: null, line_end_date: null, first_seen_date: "2026-12-01", last_seen_date: "2026-12-20",
  last_impressions_date: null, mapped_line_id: null,
};
const LINES = [{ id: 4, campaign_name: "Campaña", line_number: 1, start_date: "2026-12-01", end_date: "2026-12-31", dsp_id: 1, dsp_name: "Adform" }];

const routes = () => ({
  "GET /ingestion-exceptions?status=open": () => reply(200, [EXCEPTION]),
  "GET /campaign-lines/unmapped": () => reply(200, LINES),
  "GET /dsp-catalog?limit=50&offset=0": () => reply(200, { items: [ITEM, { ...ITEM, external_line_item_id: "L-2", line_item_name: "Video", mapped_line_id: 7 }], total: 2, limit: 50, offset: 0 }),
});

const CASES: { name: string; page: () => ReactElement; opener: string; dialog: string }[] = [
  { name: "resolve", page: () => <ExceptionsPage />, opener: "Resolver excepción 5", dialog: "Resolver excepción 5" },
  { name: "link from the queue", page: () => <ExceptionsPage />, opener: "Vincular a una línea (excepción 5)", dialog: "Vincular la excepción 5 a una línea" },
  { name: "link from the catalogue", page: () => <DspCatalogPage />, opener: "Vincular a una línea: Navidad / Display", dialog: "Vincular la pareja a una línea" },
  { name: "unlink", page: () => <DspCatalogPage />, opener: "Desvincular: Navidad / Video", dialog: "Desvincular la pareja" },
];

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe.each(CASES)("the $name dialog", ({ page, opener, dialog }) => {
  async function open(user: ReturnType<typeof userEvent.setup>) {
    installRoutes(routes());
    renderAuthenticated(page());
    const button = await screen.findByRole("button", { name: opener });
    await user.click(button);
    return { button, element: await screen.findByRole("dialog", { name: dialog }) };
  }

  it("is a native, open <dialog> named by its heading", async () => {
    const { element } = await open(userEvent.setup());

    expect(element.tagName).toBe("DIALOG");
    expect(element).toHaveAttribute("open");
    expect(element).toHaveAccessibleName(dialog);
  });

  it("takes the focus when it opens", async () => {
    const { element } = await open(userEvent.setup());

    expect(element.contains(document.activeElement)).toBe(true);
  });

  it("closes with Escape and gives the focus back to the button that opened it", async () => {
    const user = userEvent.setup();
    const { button } = await open(user);

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });

  it("closes with «Cancelar» and gives the focus back to the button that opened it", async () => {
    const user = userEvent.setup();
    const { button } = await open(user);

    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });
});
