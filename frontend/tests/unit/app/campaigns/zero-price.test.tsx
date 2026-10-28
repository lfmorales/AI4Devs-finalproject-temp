import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { User } from "oidc-client-ts";

import {
  TWO_MONTH_PREVIEW,
  fieldNear,
  fillCampaignHeader,
  fillLine,
  installFakeApi,
  lineSection,
  renderForm,
  setValue,
} from "../../../helpers/campaign-form";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "t", expired: false } as unknown as User),
    removeUser: vi.fn(),
  }),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

const submit = () => fireEvent.click(screen.getByRole("button", { name: "Registrar campaña" }));

async function filledForm(cpm: string, volume = "6100") {
  const api = installFakeApi({ preview: () => TWO_MONTH_PREVIEW, register: () => ({ status: 201, body: {} }) });
  await renderForm();
  fillCampaignHeader();
  fillLine(0, volume);
  setValue(fieldNear(lineSection(0), /CPM/), cpm);
  return api;
}

describe("registering a line without a price", () => {
  it("sends a sale CPM of 0.00 with the volume, to register a line without a price", async () => {
    const api = await filledForm("0.00");

    submit();

    await waitFor(() => expect(api.to("POST", "/campaigns")).toHaveLength(1));
    const [line] = api.to("POST", "/campaigns")[0]!.body!.lines as Record<string, unknown>[];
    expect(line!.sale_cpm).toBe("0.00");
    expect(line!.contracted_impressions).toBe(6100);
  });

  it("accepts a plain 0", async () => {
    const api = await filledForm("0");

    submit();

    await waitFor(() => expect(api.to("POST", "/campaigns")).toHaveLength(1));
  });

  it("shows no CPM error for a price of 0", async () => {
    await filledForm("0.00");

    submit();

    await waitFor(() => expect(screen.queryByText("CPM (venta) debe ser un número decimal válido")).not.toBeInTheDocument());
    expect(within(lineSection(0)).queryByText("El CPM (venta) no puede ser negativo")).not.toBeInTheDocument();
  });
});

describe("a negative price", () => {
  it("shows the error in Spanish next to the field and sends nothing", async () => {
    const api = await filledForm("-1.00");

    submit();

    expect(await within(lineSection(0)).findByText("El CPM (venta) no puede ser negativo")).toBeInTheDocument();
    expect(api.to("POST", "/campaigns")).toHaveLength(0);
  });
});

describe("the volume of a line without a price", () => {
  it("must still be above 0: the field refuses 0 and nothing is sent", async () => {
    const api = await filledForm("0.00", "0");
    const volume = fieldNear(lineSection(0), /Impresiones contratadas/);

    submit();

    expect(volume).toBeInvalid();
    expect((volume as HTMLInputElement).validity.rangeUnderflow).toBe(true);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(api.to("POST", "/campaigns")).toHaveLength(0);
  });

  it("keeps the volume field at a minimum of 1", async () => {
    await filledForm("0.00");

    expect(fieldNear(lineSection(0), /Impresiones contratadas/)).toHaveAttribute("min", "1");
  });
});
