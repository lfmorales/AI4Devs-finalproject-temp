import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { User } from "oidc-client-ts";

import {
  TWO_MONTH_PREVIEW,
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

const MESSAGES: Record<string, string> = {
  line_dates_outside_campaign: "Las fechas de la línea deben estar dentro de las fechas de la campaña.",
  line_dates_invalid: "La fecha de fin de la línea no puede ser anterior a la de inicio.",
  flight_volumes_incomplete: "El reparto debe cubrir exactamente los meses en los que corre la línea.",
  flight_volumes_mismatch: "Los volúmenes mensuales deben sumar el total de la línea.",
  flight_volume_not_positive: "Cada volumen mensual debe ser positivo.",
  volume_too_small_for_flights: "El volumen de la línea es demasiado pequeño para dar impresiones a todos los meses.",
};
const PREVIEW_CODES = ["line_dates_outside_campaign", "line_dates_invalid", "volume_too_small_for_flights"];
const REGISTRATION_CODES = Object.keys(MESSAGES);
const SEVERAL = "En alguna de estas líneas: ";

const submit = () => fireEvent.click(screen.getByRole("button", { name: "Registrar campaña" }));
const calculate = (index: number) =>
  fireEvent.click(within(lineSection(index)).getByRole("button", { name: "Calcular reparto" }));
const reject = (code: string) => ({ status: 422, body: { code, message: "backend text" } });
const addLine = () => fireEvent.click(screen.getByRole("button", { name: "Añadir línea" }));
const useOwnDates = (index: number, start = "2026-08-05", end = "2026-09-05") => {
  const line = lineSection(index);
  fireEvent.click(within(line).getByLabelText("Heredar las fechas de la campaña"));
  setValue(within(line).getByLabelText("Inicio de la línea"), start);
  setValue(within(line).getByLabelText("Fin de la línea"), end);
};

async function manualLine(index: number) {
  calculate(index);
  await within(lineSection(index)).findByText(/Suma 6100 de 6100/);
  setValue(within(lineSection(index)).getByLabelText("Volumen 08/2026"), "3200");
  setValue(within(lineSection(index)).getByLabelText("Volumen 09/2026"), "2900");
}

describe("backend codes of the preview, on the exact line", () => {
  it.each(PREVIEW_CODES)("shows %s in Spanish on line 2 only, when «Calcular reparto» fails", async (code) => {
    installFakeApi({ preview: (body) => (body.contracted_impressions === 2 ? reject(code) : TWO_MONTH_PREVIEW) });
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    addLine();
    fillLine(1, "2");

    calculate(1);

    expect(await within(lineSection(1)).findByText(MESSAGES[code]!)).toBeInTheDocument();
    expect(within(lineSection(0)).queryByText(MESSAGES[code]!)).not.toBeInTheDocument();
  });

  it.each(PREVIEW_CODES)("shows %s in Spanish on line 2 only, when the silent preview fails", async (code) => {
    const api = installFakeApi({
      preview: (body) => (body.contracted_impressions === 2 ? reject(code) : TWO_MONTH_PREVIEW),
      register: () => ({ status: 201, body: {} }),
    });
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    addLine();
    fillLine(1, "2");

    submit();

    expect(await within(lineSection(1)).findByText(MESSAGES[code]!)).toBeInTheDocument();
    expect(within(lineSection(0)).queryByText(MESSAGES[code]!)).not.toBeInTheDocument();
    expect(api.to("POST", "/campaigns")).toHaveLength(0);
  });
});

describe("registration 422 codes", () => {
  it.each(REGISTRATION_CODES)("shows %s in Spanish and not as generic text", async (code) => {
    installFakeApi({ preview: () => TWO_MONTH_PREVIEW, register: () => reject(code) });
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    useOwnDates(0);
    await manualLine(0);

    submit();

    await waitFor(() => expect(screen.getAllByText(MESSAGES[code]!).length).toBeGreaterThan(0));
    expect(screen.queryByText("Error al registrar la campaña. Intenta de nuevo más tarde.")).not.toBeInTheDocument();
    expect(screen.queryByText("backend text")).not.toBeInTheDocument();
  });

  it("puts the error on the only candidate line, without the «alguna» wording", async () => {
    installFakeApi({ preview: () => TWO_MONTH_PREVIEW, register: () => reject("flight_volumes_mismatch") });
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    addLine();
    fillLine(1);
    await manualLine(1); // only line 2 has a manual split

    submit();

    expect(await within(lineSection(1)).findAllByText(MESSAGES.flight_volumes_mismatch!)).not.toHaveLength(0);
    expect(within(lineSection(0)).queryByText(MESSAGES.flight_volumes_mismatch!)).not.toBeInTheDocument();
    expect(screen.queryByText(new RegExp(SEVERAL))).not.toBeInTheDocument();
  });

  it("puts the error on every candidate line when there are several, saying so", async () => {
    installFakeApi({ preview: () => TWO_MONTH_PREVIEW, register: () => reject("line_dates_outside_campaign") });
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    useOwnDates(0);
    addLine();
    fillLine(1);
    useOwnDates(1, "2026-08-10", "2026-09-10");
    addLine();
    fillLine(2); // inherits: not a candidate

    submit();

    const expected = `${SEVERAL}${MESSAGES.line_dates_outside_campaign!}`;
    expect(await within(lineSection(0)).findByText(expected)).toBeInTheDocument();
    expect(within(lineSection(1)).getByText(expected)).toBeInTheDocument();
    expect(within(lineSection(2)).queryByText(expected)).not.toBeInTheDocument();
  });

  it("shows the error at form level when no line can be the cause", async () => {
    installFakeApi({ preview: () => TWO_MONTH_PREVIEW, register: () => reject("line_dates_invalid") });
    await renderForm();
    fillCampaignHeader();
    fillLine(0); // inherits its dates: nothing of its own to be wrong

    submit();

    expect(await screen.findByText(MESSAGES.line_dates_invalid!)).toBeInTheDocument();
    expect(within(lineSection(0)).queryByText(MESSAGES.line_dates_invalid!)).not.toBeInTheDocument();
  });

  it("treats volume_too_small_for_flights as a fault of the proportional lines", async () => {
    installFakeApi({ preview: () => TWO_MONTH_PREVIEW, register: () => reject("volume_too_small_for_flights") });
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    addLine();
    fillLine(1);
    await manualLine(1);

    submit();

    expect(await within(lineSection(0)).findByText(MESSAGES.volume_too_small_for_flights!)).toBeInTheDocument();
    expect(within(lineSection(1)).queryByText(MESSAGES.volume_too_small_for_flights!)).not.toBeInTheDocument();
  });
});
