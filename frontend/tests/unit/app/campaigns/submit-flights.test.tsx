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

const REGISTERED = { status: 201, body: {} };
const submit = () => fireEvent.click(screen.getByRole("button", { name: "Registrar campaña" }));
const calculate = (index: number) =>
  fireEvent.click(within(lineSection(index)).getByRole("button", { name: "Calcular reparto" }));

async function registeredLines(api: ReturnType<typeof installFakeApi>) {
  await waitFor(() => expect(api.to("POST", "/campaigns")).toHaveLength(1));
  return api.to("POST", "/campaigns")[0]!.body!.lines as Record<string, unknown>[];
}

async function manualSplit(api: ReturnType<typeof installFakeApi>, firstMonth = "3000") {
  await renderForm();
  fillCampaignHeader();
  fillLine(0);
  calculate(0);
  await within(lineSection(0)).findByText(/Suma 6100 de 6100/);
  setValue(within(lineSection(0)).getByLabelText("Volumen 08/2026"), firstMonth);
  return api;
}

describe("submitting lines with flights", () => {
  it("sends monthly_volumes for a manual split, and only then", async () => {
    const api = installFakeApi({ preview: () => TWO_MONTH_PREVIEW, register: () => REGISTERED });
    await manualSplit(api, "3200");
    setValue(within(lineSection(0)).getByLabelText("Volumen 09/2026"), "2900");

    submit();

    const [line] = await registeredLines(api);
    expect(line!.monthly_volumes).toEqual([
      { year: 2026, month: 8, volume: 3200 },
      { year: 2026, month: 9, volume: 2900 },
    ]);
  });

  it("sends no monthly_volumes for a proportional split that was only calculated", async () => {
    const api = installFakeApi({ preview: () => TWO_MONTH_PREVIEW, register: () => REGISTERED });
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    calculate(0);
    await within(lineSection(0)).findByText(/Suma 6100 de 6100/);

    submit();

    const [line] = await registeredLines(api);
    expect(Object.keys(line!)).not.toContain("monthly_volumes");
    expect(api.to("POST", "/flights/preview")).toHaveLength(1); // not previewed again
  });

  it("sends no monthly_volumes after the split is restored to proportional", async () => {
    const api = installFakeApi({ preview: () => TWO_MONTH_PREVIEW, register: () => REGISTERED });
    await manualSplit(api);
    fireEvent.click(within(lineSection(0)).getByRole("button", { name: "Restablecer reparto proporcional" }));

    submit();

    const [line] = await registeredLines(api);
    expect(Object.keys(line!)).not.toContain("monthly_volumes");
  });

  it("previews silently every line that has no preview before registering", async () => {
    const api = installFakeApi({ preview: () => TWO_MONTH_PREVIEW, register: () => REGISTERED });
    await renderForm();
    fillCampaignHeader();
    fillLine(0);

    submit();

    await registeredLines(api);
    const order = api.requests.filter((r) => r.method === "POST").map((r) => r.path);
    expect(order).toEqual(["/flights/preview", "/campaigns"]);
  });

  it("re-previews a stale proportional line instead of sending an old split", async () => {
    const api = installFakeApi({ preview: () => TWO_MONTH_PREVIEW, register: () => REGISTERED });
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    calculate(0);
    await within(lineSection(0)).findByText(/Suma 6100 de 6100/);
    setValue(fieldNear(lineSection(0), /Impresiones contratadas/), "7000");

    submit();

    const [line] = await registeredLines(api);
    expect(api.to("POST", "/flights/preview")).toHaveLength(2);
    expect(api.to("POST", "/flights/preview")[1]!.body).toMatchObject({ contracted_impressions: 7000 });
    expect(line!.contracted_impressions).toBe(7000);
    expect(Object.keys(line!)).not.toContain("monthly_volumes");
  });

  it("blocks a manual split whose sum differs from the total", async () => {
    const api = installFakeApi({ preview: () => TWO_MONTH_PREVIEW, register: () => REGISTERED });
    await manualSplit(api, "3000");

    submit();

    expect(await within(lineSection(0)).findAllByText("Los volúmenes mensuales deben sumar el total de la línea.")).not.toHaveLength(0);
    expect(api.to("POST", "/campaigns")).toHaveLength(0);
  });

  it("blocks a manual split with a volume that is not positive", async () => {
    const api = installFakeApi({ preview: () => TWO_MONTH_PREVIEW, register: () => REGISTERED });
    await manualSplit(api, "0");

    submit();

    expect(await within(lineSection(0)).findAllByText("Cada volumen mensual debe ser positivo.")).not.toHaveLength(0);
    expect(api.to("POST", "/campaigns")).toHaveLength(0);
  });

  it("blocks a stale manual split and asks to recalculate, never sending it", async () => {
    const api = installFakeApi({ preview: () => TWO_MONTH_PREVIEW, register: () => REGISTERED });
    await manualSplit(api, "3200");
    setValue(fieldNear(lineSection(0), /Impresiones contratadas/), "7000");

    submit();

    await screen.findByText("Por favor corrige los errores antes de enviar.");
    expect(api.to("POST", "/campaigns")).toHaveLength(0);
    expect(api.to("POST", "/flights/preview")).toHaveLength(1);
  });

  it("with two lines, shows a failed preview on that line only and does not register", async () => {
    const api = installFakeApi({
      preview: (body) => (body.contracted_impressions === 2 ? { status: 422, body: { code: "volume_too_small_for_flights", message: "x" } } : TWO_MONTH_PREVIEW),
      register: () => REGISTERED,
    });
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    fireEvent.click(screen.getByRole("button", { name: "Añadir línea" }));
    fillLine(1, "2");

    submit();

    await within(lineSection(1)).findByText(/No se pudo calcular el reparto/);
    expect(within(lineSection(0)).queryByText(/No se pudo calcular el reparto/)).not.toBeInTheDocument();
    expect(api.to("POST", "/campaigns")).toHaveLength(0);
  });

  it("sends monthly_volumes only on the manual line when two lines differ", async () => {
    const api = installFakeApi({ preview: () => TWO_MONTH_PREVIEW, register: () => REGISTERED });
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    fireEvent.click(screen.getByRole("button", { name: "Añadir línea" }));
    fillLine(1);
    calculate(1);
    await within(lineSection(1)).findByText(/Suma 6100 de 6100/);
    setValue(within(lineSection(1)).getByLabelText("Volumen 08/2026"), "3200");
    setValue(within(lineSection(1)).getByLabelText("Volumen 09/2026"), "2900");

    submit();

    const lines = await registeredLines(api);
    expect(Object.keys(lines[0]!)).not.toContain("monthly_volumes");
    expect(lines[1]!.monthly_volumes).toHaveLength(2);
  });

  it.each([
    [401, "unauthenticated"],
    [403, "forbidden"],
  ] as const)("reports a %s during the silent preview to the page", async (status, kind) => {
    const onAuthError = vi.fn();
    const api = installFakeApi({
      preview: () => ({ status, body: { code: kind, message: "x" } }),
      register: () => REGISTERED,
    });
    await renderForm(onAuthError);
    fillCampaignHeader();
    fillLine(0);

    submit();

    await waitFor(() => expect(onAuthError).toHaveBeenCalledWith(kind));
    expect(api.to("POST", "/campaigns")).toHaveLength(0);
  });

  it("reports a 401 or 403 of «Calcular reparto» to the page too", async () => {
    const onAuthError = vi.fn();
    installFakeApi({ preview: () => ({ status: 403, body: { code: "forbidden", message: "x" } }) });
    await renderForm(onAuthError);
    fillCampaignHeader();
    fillLine(0);

    calculate(0);

    await waitFor(() => expect(onAuthError).toHaveBeenCalledWith("forbidden"));
  });
});
