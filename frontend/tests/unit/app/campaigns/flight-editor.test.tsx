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

const calculate = () => within(lineSection(0)).getByRole("button", { name: "Calcular reparto" });

async function calculated() {
  const api = installFakeApi({ preview: () => TWO_MONTH_PREVIEW });
  await renderForm();
  fillCampaignHeader();
  fillLine(0);
  fireEvent.click(calculate());
  await within(lineSection(0)).findByText(/Suma 6100 de 6100/);
  return api;
}

describe("the flight editor of a line", () => {
  it("keeps «Calcular reparto» disabled until the dates and the total are valid", async () => {
    installFakeApi();
    await renderForm();
    expect(calculate()).toBeDisabled();

    fillCampaignHeader();
    expect(calculate()).toBeDisabled(); // no total yet

    setValue(fieldNear(lineSection(0), /Impresiones contratadas/), "6100");
    expect(calculate()).toBeEnabled();
  });

  it("stays disabled when the campaign's end is before its start", async () => {
    installFakeApi();
    await renderForm();
    fillCampaignHeader({ start: "2026-09-30", end: "2026-08-01" });
    fillLine(0);

    expect(calculate()).toBeDisabled();
  });

  it("stays disabled when the line's own dates fall outside the campaign", async () => {
    installFakeApi();
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    fireEvent.click(within(lineSection(0)).getByLabelText("Heredar las fechas de la campaña"));
    setValue(within(lineSection(0)).getByLabelText("Inicio de la línea"), "2026-07-01");
    setValue(within(lineSection(0)).getByLabelText("Fin de la línea"), "2026-09-01");

    expect(calculate()).toBeDisabled();
  });

  it("asks the preview with the campaign's dates and no line dates when the line inherits", async () => {
    const api = await calculated();

    expect(api.to("POST", "/flights/preview")).toHaveLength(1);
    expect(api.to("POST", "/flights/preview")[0]!.body).toEqual({
      campaign_start_date: "2026-08-01",
      campaign_end_date: "2026-09-30",
      contracted_impressions: 6100,
    });
  });

  it("asks the preview with the line's own dates when it has them", async () => {
    const api = installFakeApi({ preview: () => TWO_MONTH_PREVIEW });
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    fireEvent.click(within(lineSection(0)).getByLabelText("Heredar las fechas de la campaña"));
    setValue(within(lineSection(0)).getByLabelText("Inicio de la línea"), "2026-08-10");
    setValue(within(lineSection(0)).getByLabelText("Fin de la línea"), "2026-09-10");

    fireEvent.click(calculate());

    await waitFor(() => expect(api.to("POST", "/flights/preview")).toHaveLength(1));
    expect(api.to("POST", "/flights/preview")[0]!.body).toMatchObject({ start_date: "2026-08-10", end_date: "2026-09-10" });
  });

  it("shows the month, the window and the volume of every flight and the sum", async () => {
    await calculated();
    const line = lineSection(0);

    const rows = within(line).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByText("08/2026")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("2026-08-01 – 2026-08-31")).toBeInTheDocument();
    expect(within(rows[0]!).getByLabelText("Volumen 08/2026")).toHaveValue(3100);
    expect(within(rows[1]!).getByLabelText("Volumen 09/2026")).toHaveValue(3000);
    expect(within(line).getByText("Suma 6100 de 6100")).toBeInTheDocument();
    expect(within(line).queryByText("Reparto manual")).not.toBeInTheDocument();
  });

  it("turns into a manual split when a volume is edited, and updates the sum", async () => {
    await calculated();
    const line = lineSection(0);

    setValue(within(line).getByLabelText("Volumen 08/2026"), "3000");

    expect(within(line).getByText("Reparto manual")).toBeInTheDocument();
    expect(within(line).getByText("Suma 6000 de 6100")).toBeInTheDocument();
    expect(within(line).getByText("Los volúmenes mensuales deben sumar el total de la línea.")).toBeInTheDocument();
  });

  it("explains a split that does not cover positive volumes", async () => {
    await calculated();
    const line = lineSection(0);

    setValue(within(line).getByLabelText("Volumen 08/2026"), "0");

    expect(within(line).getByText("Cada volumen mensual debe ser positivo.")).toBeInTheDocument();
  });

  it("restores the proportional split with «Restablecer reparto proporcional»", async () => {
    await calculated();
    const line = lineSection(0);
    setValue(within(line).getByLabelText("Volumen 08/2026"), "3000");

    fireEvent.click(within(line).getByRole("button", { name: "Restablecer reparto proporcional" }));

    expect(within(line).getByLabelText("Volumen 08/2026")).toHaveValue(3100);
    expect(within(line).getByText("Suma 6100 de 6100")).toBeInTheDocument();
    expect(within(line).queryByText("Reparto manual")).not.toBeInTheDocument();
    expect(within(line).queryByRole("button", { name: "Restablecer reparto proporcional" })).not.toBeInTheDocument();
  });

  it.each([
    ["the total volume", () => setValue(fieldNear(lineSection(0), /Impresiones contratadas/), "7000")],
    ["the campaign's start", () => setValue(fieldNear(screen, /Fecha de inicio \*/), "2026-08-02")],
    ["the campaign's end", () => setValue(fieldNear(screen, /Fecha de fin \*/), "2026-09-29")],
    ["the line's own dates", () => {
      fireEvent.click(within(lineSection(0)).getByLabelText("Heredar las fechas de la campaña"));
    }],
  ])("invalidates the preview when %s changes", async (_name, change) => {
    await calculated();
    const line = lineSection(0);

    change();

    expect(within(line).queryByRole("table")).not.toBeInTheDocument();
    expect(within(line).getByText(/vuelve a calcular el reparto/i)).toBeInTheDocument();
  });

  it("invalidates the preview when an own date of the line is edited", async () => {
    await calculated();
    const line = lineSection(0);
    fireEvent.click(within(line).getByLabelText("Heredar las fechas de la campaña"));
    setValue(within(line).getByLabelText("Inicio de la línea"), "2026-08-05");
    setValue(within(line).getByLabelText("Fin de la línea"), "2026-09-05");
    fireEvent.click(calculate());
    await within(line).findByText(/Suma 6100 de 6100/);

    setValue(within(line).getByLabelText("Fin de la línea"), "2026-09-06");

    expect(within(line).queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows the table again after recalculating", async () => {
    await calculated();
    const line = lineSection(0);
    setValue(fieldNear(line, /Impresiones contratadas/), "7000");

    fireEvent.click(calculate());

    await waitFor(() => expect(within(line).getByRole("table")).toBeInTheDocument());
    expect(within(line).queryByText(/vuelve a calcular el reparto/i)).not.toBeInTheDocument();
  });
});
