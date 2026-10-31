import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { User } from "oidc-client-ts";

import { CreateCampaignForm } from "@/features/campaigns/CreateCampaignForm";
import { AuthContext, type AuthContextValue } from "@/lib/auth/AuthContext";
import {
  API_URL,
  TWO_MONTH_PREVIEW,
  fillCampaignHeader,
  fillLine,
  installFakeApi,
  lineSection,
  renderForm,
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

const CAMPAIGN_LABELS = [
  "Nombre de la campaña *",
  "Nombre mostrado *",
  "Agencia *",
  "Anunciante *",
  "Tipo de campaña *",
  "Sector *",
  "Comercial *",
  "Fecha de inicio *",
  "Fecha de fin *",
  "Referencia de orden *",
  "Fecha de recepción *",
];
const LINE_LABELS = [
  "DSP *",
  "Canal *",
  "Formato *",
  "Alcance *",
  "Descripción del mercado *",
  "Impresiones contratadas *",
  "CPM (venta) *",
];

const submit = () => fireEvent.click(screen.getByRole("button", { name: "Registrar campaña" }));
const addLine = () => fireEvent.click(screen.getByRole("button", { name: "Añadir línea" }));
const reject = (code: string) => ({ status: 422, body: { code, message: "backend text" } });

describe("the controls of the new-campaign form have an accessible name", () => {
  it.each(CAMPAIGN_LABELS)("finds «%s» by its exact label", async (label) => {
    installFakeApi();
    await renderForm();

    expect(screen.getByLabelText(label, { exact: true })).toBeInTheDocument();
  });

  it.each(LINE_LABELS)("finds «%s» of the line by its exact label", async (label) => {
    installFakeApi();
    await renderForm();

    expect(within(lineSection(0)).getByLabelText(label, { exact: true })).toBeInTheDocument();
  });

  it("ties each control to a label that reaches it through the label's own text, with a different id every time", async () => {
    installFakeApi();
    await renderForm();
    addLine();

    const form = document.querySelector("form")!;
    const ids = Array.from(form.querySelectorAll("[id]")).map((element) => element.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const label of Array.from(form.querySelectorAll("label"))) {
      expect(label.htmlFor, `the label «${label.textContent?.trim()}» points at a control`).not.toBe("");
      expect(form.querySelector(`#${CSS.escape(label.htmlFor)}`)).not.toBeNull();
    }
  });

  it("gives each line's controls their own label in a form with two lines", async () => {
    installFakeApi();
    await renderForm();
    addLine();

    const [first, second] = [lineSection(0), lineSection(1)];
    for (const label of LINE_LABELS) {
      const ofFirst = within(first).getByLabelText(label, { exact: true });
      const ofSecond = within(second).getByLabelText(label, { exact: true });
      expect(ofFirst).not.toBe(ofSecond);
      expect(first.contains(ofFirst)).toBe(true);
      expect(second.contains(ofSecond)).toBe(true);
    }
    // A change in the second line's field is not seen in the first line's.
    fireEvent.change(within(second).getByLabelText("Descripción del mercado *"), { target: { value: "Segunda" } });
    expect(within(first).getByLabelText("Descripción del mercado *")).toHaveValue("");
    expect(within(second).getByLabelText("Descripción del mercado *")).toHaveValue("Segunda");
  });
});

describe("the errors of the form", () => {
  it("shows the form notice with role alert", async () => {
    installFakeApi();
    await renderForm();

    submit();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Por favor corrige los errores antes de enviar.");
  });

  it("shows the load error with role alert", async () => {
    process.env.NEXT_PUBLIC_API_URL = API_URL;
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 500, headers: { "Content-Type": "application/json" } })));
    const auth: AuthContextValue = {
      session: { status: "authenticated", email: "user@example.com", idToken: "token" },
      signIn: vi.fn(),
      signOut: vi.fn(),
    };

    render(
      <AuthContext.Provider value={auth}>
        <CreateCampaignForm />
      </AuthContext.Provider>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Error al cargar los datos maestros. Intenta de nuevo más tarde.");
  });

  it("describes a campaign field with its own error", async () => {
    installFakeApi();
    await renderForm();

    expect(screen.getByLabelText("Nombre de la campaña *")).not.toHaveAccessibleDescription();
    submit();

    await waitFor(() => expect(screen.getByLabelText("Nombre de la campaña *")).toHaveAccessibleDescription(/\S/));
    expect(screen.getByLabelText("Agencia *")).toHaveAccessibleDescription(/\S/);
  });

  it("describes only the controls of the line that has the error", async () => {
    installFakeApi({ preview: () => TWO_MONTH_PREVIEW });
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    addLine();

    submit();

    await waitFor(() => expect(within(lineSection(1)).getByLabelText("DSP *")).toHaveAccessibleDescription(/\S/));
    expect(within(lineSection(1)).getByLabelText("CPM (venta) *")).toHaveAccessibleDescription(/\S/);
    expect(within(lineSection(0)).getByLabelText("DSP *")).not.toHaveAccessibleDescription();
    expect(within(lineSection(0)).getByLabelText("CPM (venta) *")).not.toHaveAccessibleDescription();
  });

  it("shows the error of a line's preview with role alert inside that line only", async () => {
    installFakeApi({ preview: (body) => (body.contracted_impressions === 2 ? reject("volume_too_small_for_flights") : TWO_MONTH_PREVIEW) });
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    addLine();
    fillLine(1, "2");

    fireEvent.click(within(lineSection(1)).getByRole("button", { name: "Calcular reparto" }));

    const alert = await within(lineSection(1)).findByRole("alert");
    expect(alert).toHaveTextContent("El volumen de la línea es demasiado pequeño para dar impresiones a todos los meses.");
    expect(within(lineSection(0)).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the problem of a manual split with role alert", async () => {
    installFakeApi({ preview: () => TWO_MONTH_PREVIEW });
    await renderForm();
    fillCampaignHeader();
    fillLine(0);
    fireEvent.click(within(lineSection(0)).getByRole("button", { name: "Calcular reparto" }));
    const volume = await within(lineSection(0)).findByLabelText("Volumen 08/2026");

    fireEvent.change(volume, { target: { value: "3000" } });

    expect(await within(lineSection(0)).findByRole("alert")).toHaveTextContent("Los volúmenes mensuales deben sumar el total de la línea.");
  });
});
