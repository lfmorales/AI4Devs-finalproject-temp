import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import DspCatalogPage from "@/app/(authenticated)/dsp-catalog/page";
import ExceptionsPage from "@/app/(authenticated)/exceptions/page";
import { AdformName } from "@/features/linking/AdformName";
import type { DspCatalogItem } from "@/lib/api/dsp-catalog";
import type { IngestionException } from "@/lib/api/exceptions";
import { installRoutes, renderAuthenticated, reply } from "../../../helpers/api-pages";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

const MASKED = { filter: "blur(6px)", userSelect: "none", pointerEvents: "none" };

const ITEM: DspCatalogItem = {
  dsp_id: 1, external_campaign_id: "C-1", external_line_item_id: "L-1", campaign_name: "Navidad 2026", line_item_name: "Display ES",
  line_start_date: "2026-12-01", line_end_date: "2026-12-31", first_seen_date: "2026-12-01", last_seen_date: "2026-12-20",
  last_impressions_date: "2026-12-19", mapped_line_id: 7,
};

const EXCEPTION: IngestionException = {
  id: 5, exception_type: "unmatched_delivery", status: "open", ingestion_batch_id: 3, dsp_id: 1,
  external_campaign_id: "C-9", external_line_item_id: "L-9", campaign_line_id: null, campaign_period_id: null,
  first_date: "2026-08-03", last_date: "2026-08-08", days: 3, impressions_total: 40000, clicks_total: 11000,
  resolved_at: null, resolved_by: null, note: null, campaign_name: "Navidad 2026", line_item_name: "Display ES",
};

beforeEach(() => vi.clearAllMocks());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("AdformName", () => {
  it("shows the name normally when the variable is not set", () => {
    render(<AdformName name="Navidad 2026" />);

    expect(screen.getByText("Navidad 2026")).not.toHaveStyle({ filter: "blur(6px)" });
  });

  it.each(["false", "", "TRUE", "1"])("shows the name normally when the variable is %j", (value) => {
    vi.stubEnv("NEXT_PUBLIC_MASK_NAMES", value);

    render(<AdformName name="Navidad 2026" />);

    expect(screen.getByText("Navidad 2026")).not.toHaveStyle({ filter: "blur(6px)" });
  });

  it("blurs the name, makes it unselectable and keeps the pointer from reaching it when the variable is true", () => {
    vi.stubEnv("NEXT_PUBLIC_MASK_NAMES", "true");

    render(<AdformName name="Navidad 2026" />);

    const name = screen.getByText("Navidad 2026");
    expect(name).toHaveStyle(MASKED);
    expect(name).not.toHaveAttribute("title");
  });
});

describe("the masking in the pages", () => {
  it("blurs the catalogue's campaign and line names, and the names in the unlink confirmation", async () => {
    vi.stubEnv("NEXT_PUBLIC_MASK_NAMES", "true");
    const user = userEvent.setup();
    installRoutes({ "GET /dsp-catalog?limit=50&offset=0": () => reply(200, { items: [ITEM], total: 1, limit: 50, offset: 0 }) });
    renderAuthenticated(<DspCatalogPage />);
    const table = await screen.findByRole("table", { name: "Catálogo Adform" });

    expect(screen.getAllByText("Navidad 2026")).toHaveLength(1);
    for (const name of ["Navidad 2026", "Display ES"]) expect(screen.getByText(name)).toHaveStyle(MASKED);
    expect(table).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Desvincular: Navidad 2026 / Display ES" }));
    const dialog = screen.getByRole("dialog", { name: "Desvincular la pareja" });
    for (const masked of dialog.querySelectorAll("[data-adform-name]")) expect(masked).toHaveStyle(MASKED);
    expect(dialog.querySelectorAll("[data-adform-name]")).toHaveLength(2);
  });

  it("shows the catalogue names normally without the variable", async () => {
    installRoutes({ "GET /dsp-catalog?limit=50&offset=0": () => reply(200, { items: [ITEM], total: 1, limit: 50, offset: 0 }) });

    renderAuthenticated(<DspCatalogPage />);

    await screen.findByRole("table", { name: "Catálogo Adform" });
    for (const name of ["Navidad 2026", "Display ES"]) expect(screen.getByText(name)).not.toHaveStyle({ filter: "blur(6px)" });
  });

  it("blurs the names in the exception queue, but not the «Sin nombre en el catálogo» text", async () => {
    vi.stubEnv("NEXT_PUBLIC_MASK_NAMES", "true");
    installRoutes({
      "GET /ingestion-exceptions?status=open": () => reply(200, [EXCEPTION, { ...EXCEPTION, id: 6, line_item_name: null }]),
    });
    renderAuthenticated(<ExceptionsPage />);

    await screen.findByRole("table", { name: "Cola de excepciones" });

    for (const name of screen.getAllByText("Navidad 2026")) expect(name).toHaveStyle(MASKED);
    expect(screen.getByText("Display ES")).toHaveStyle(MASKED);
    expect(screen.getByText("Sin nombre en el catálogo")).not.toHaveStyle({ filter: "blur(6px)" });
  });

  it("shows the queue names normally without the variable", async () => {
    installRoutes({ "GET /ingestion-exceptions?status=open": () => reply(200, [EXCEPTION]) });

    renderAuthenticated(<ExceptionsPage />);

    await screen.findByRole("table", { name: "Cola de excepciones" });
    expect(screen.getByText("Display ES")).not.toHaveStyle({ filter: "blur(6px)" });
  });
});
