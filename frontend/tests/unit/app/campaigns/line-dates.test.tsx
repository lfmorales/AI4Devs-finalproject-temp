import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { User } from "oidc-client-ts";

import {
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

const INHERIT = "Heredar las fechas de la campaña";

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

async function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Registrar campaña" }));
}

describe("line dates in the new campaign form", () => {
  it("inherits the campaign's dates by default and shows no date fields", async () => {
    installFakeApi();
    await renderForm();

    const line = lineSection(0);
    expect(within(line).getByLabelText(INHERIT)).toBeChecked();
    expect(within(line).queryByLabelText("Inicio de la línea")).not.toBeInTheDocument();
    expect(within(line).queryByLabelText("Fin de la línea")).not.toBeInTheDocument();
  });

  it("shows the start and end fields when the box is cleared", async () => {
    installFakeApi();
    await renderForm();

    fireEvent.click(within(lineSection(0)).getByLabelText(INHERIT));

    expect(within(lineSection(0)).getByLabelText("Inicio de la línea")).toBeInTheDocument();
    expect(within(lineSection(0)).getByLabelText("Fin de la línea")).toBeInTheDocument();
  });

  it("sends no line dates when the line inherits", async () => {
    const api = installFakeApi({
      preview: () => ({ status: 200, body: { start_date: "2026-08-01", end_date: "2026-09-30", flights: [] } }),
      register: () => ({ status: 201, body: {} }),
    });
    await renderForm();
    fillCampaignHeader();
    fillLine(0);

    await submit();

    await waitFor(() => expect(api.to("POST", "/campaigns")).toHaveLength(1));
    const line = (api.to("POST", "/campaigns")[0]!.body!.lines as Record<string, unknown>[])[0]!;
    expect(Object.keys(line)).not.toContain("start_date");
    expect(Object.keys(line)).not.toContain("end_date");
  });

  it("sends the line's own dates when the box is cleared", async () => {
    const api = installFakeApi({
      preview: () => ({ status: 200, body: { start_date: "2026-08-10", end_date: "2026-09-10", flights: [] } }),
      register: () => ({ status: 201, body: {} }),
    });
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    fireEvent.click(within(lineSection(0)).getByLabelText(INHERIT));
    setValue(within(lineSection(0)).getByLabelText("Inicio de la línea"), "2026-08-10");
    setValue(within(lineSection(0)).getByLabelText("Fin de la línea"), "2026-09-10");

    await submit();

    await waitFor(() => expect(api.to("POST", "/campaigns")).toHaveLength(1));
    const line = (api.to("POST", "/campaigns")[0]!.body!.lines as Record<string, unknown>[])[0]!;
    expect(line).toMatchObject({ start_date: "2026-08-10", end_date: "2026-09-10" });
  });

  it("blocks the submit and says so beside the field when the dates fall outside the campaign", async () => {
    const api = installFakeApi();
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    fireEvent.click(within(lineSection(0)).getByLabelText(INHERIT));
    setValue(within(lineSection(0)).getByLabelText("Inicio de la línea"), "2026-07-15");
    setValue(within(lineSection(0)).getByLabelText("Fin de la línea"), "2026-10-15");

    await submit();

    expect(await within(lineSection(0)).findByText(/inicio de la línea debe estar dentro de las fechas de la campaña/i)).toBeInTheDocument();
    expect(within(lineSection(0)).getByText(/fin de la línea debe estar dentro de las fechas de la campaña/i)).toBeInTheDocument();
    expect(api.to("POST", "/campaigns")).toHaveLength(0);
  });

  it("blocks an end before the start", async () => {
    const api = installFakeApi();
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    fireEvent.click(within(lineSection(0)).getByLabelText(INHERIT));
    setValue(within(lineSection(0)).getByLabelText("Inicio de la línea"), "2026-09-10");
    setValue(within(lineSection(0)).getByLabelText("Fin de la línea"), "2026-09-01");

    await submit();

    expect(await within(lineSection(0)).findByText(/no puede ser anterior a la de inicio/i)).toBeInTheDocument();
    expect(api.to("POST", "/campaigns")).toHaveLength(0);
  });
});
