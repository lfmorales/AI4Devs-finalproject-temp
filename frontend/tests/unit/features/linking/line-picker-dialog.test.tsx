import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { LinePickerDialog } from "@/features/linking/LinePickerDialog";
import type { UnmappedLine } from "@/lib/api/dsp-catalog";
import { installRoutes, renderAuthenticated, reply, type FakeReply } from "../../../helpers/api-pages";

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({ id_token: "token", expired: false }),
    removeUser: vi.fn(),
  }),
}));

const UNMAPPED = "GET /campaign-lines/unmapped";

const LINES: UnmappedLine[] = [
  { id: 4, campaign_name: "Campaña Navidad", line_number: 1, start_date: "2026-12-01", end_date: "2026-12-31", dsp_id: 1, dsp_name: "Adform" },
  { id: 8, campaign_name: "Campaña Verano", line_number: 2, start_date: "2026-07-01", end_date: "2026-08-31", dsp_id: 2, dsp_name: "Equativ" },
];

function renderDialog(overrides: Partial<Parameters<typeof LinePickerDialog>[0]> = {}) {
  const props = {
    label: "Vincular a una línea", submitting: false, problem: null,
    onConfirm: vi.fn(), onCancel: vi.fn(), onFatal: vi.fn(), ...overrides,
  };
  renderAuthenticated(<LinePickerDialog {...props} />);
  return props;
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe("the line picker dialog", () => {
  it("lists the unmapped lines with campaign, line number, dates and DSP, as options of a labelled group", async () => {
    installRoutes({ [UNMAPPED]: () => reply(200, LINES) });

    renderDialog();

    const dialog = await screen.findByRole("dialog", { name: "Vincular a una línea" });
    const group = await within(dialog).findByRole("radiogroup", { name: "Líneas sin mapeo" });
    const options = within(group).getAllByRole("radio");
    expect(options).toHaveLength(2);
    expect(within(group).getByRole("radio", { name: "Campaña Navidad, línea 1, del 2026-12-01 al 2026-12-31, Adform" })).toBeInTheDocument();
    expect(within(group).getByRole("radio", { name: "Campaña Verano, línea 2, del 2026-07-01 al 2026-08-31, Equativ" })).toBeInTheDocument();
  });

  it("filters the lines by the text typed, in any case, over campaign, line number and DSP", async () => {
    const user = userEvent.setup();
    installRoutes({ [UNMAPPED]: () => reply(200, LINES) });
    renderDialog();
    const search = await screen.findByLabelText("Buscar línea");

    await user.type(search, "nAvIdAd");
    expect(screen.getAllByRole("radio")).toHaveLength(1);
    expect(screen.getByRole("radio", { name: /Navidad/ })).toBeInTheDocument();

    await user.clear(search);
    await user.type(search, "equativ");
    expect(screen.getByRole("radio", { name: /Verano/ })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /Navidad/ })).not.toBeInTheDocument();
  });

  it("says nothing matches, apart from the empty and the loading states", async () => {
    const user = userEvent.setup();
    installRoutes({ [UNMAPPED]: () => reply(200, LINES) });
    renderDialog();

    await user.type(await screen.findByLabelText("Buscar línea"), "zzz");

    expect(screen.getByText("Ninguna línea coincide con la búsqueda")).toBeInTheDocument();
    expect(screen.queryByText("No hay líneas sin mapeo")).not.toBeInTheDocument();
  });

  it("keeps «Confirmar vinculación» disabled until a line is chosen, then confirms that line", async () => {
    const user = userEvent.setup();
    installRoutes({ [UNMAPPED]: () => reply(200, LINES) });
    const props = renderDialog();
    const confirm = await screen.findByRole("button", { name: "Confirmar vinculación" });
    expect(confirm).toBeDisabled();

    await user.click(screen.getByRole("radio", { name: /Verano/ }));
    expect(confirm).toBeEnabled();
    await user.click(confirm);

    expect(props.onConfirm).toHaveBeenCalledWith(LINES[1]);
  });

  it("calls onCancel and confirms nothing when cancelled", async () => {
    const user = userEvent.setup();
    installRoutes({ [UNMAPPED]: () => reply(200, LINES) });
    const props = renderDialog();

    await user.click(await screen.findByRole("button", { name: "Cancelar" }));

    expect(props.onCancel).toHaveBeenCalledTimes(1);
    expect(props.onConfirm).not.toHaveBeenCalled();
  });

  it("shows the problem it is given inside the dialog, and disables the buttons while submitting", async () => {
    installRoutes({ [UNMAPPED]: () => reply(200, LINES) });

    renderDialog({ problem: "Esta pareja ya está vinculada.", submitting: true });

    const dialog = await screen.findByRole("dialog", { name: "Vincular a una línea" });
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Esta pareja ya está vinculada.");
    expect(within(dialog).getByRole("button", { name: "Cancelar" })).toBeDisabled();
  });

  it("says it is loading, and neither that there are no lines nor an error, while the list is pending", async () => {
    installRoutes({ [UNMAPPED]: () => new Promise<FakeReply>(() => {}) });

    renderDialog();

    expect(await screen.findByText("Cargando líneas…")).toBeInTheDocument();
    expect(screen.queryByText("No hay líneas sin mapeo")).not.toBeInTheDocument();
    expect(screen.queryByText(/No se pudieron cargar/)).not.toBeInTheDocument();
  });

  it("says there are no unmapped lines when the list is empty", async () => {
    installRoutes({ [UNMAPPED]: () => reply(200, []) });

    renderDialog();

    expect(await screen.findByText("No hay líneas sin mapeo")).toBeInTheDocument();
    expect(screen.queryByText("Cargando líneas…")).not.toBeInTheDocument();
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
  });

  it("says the lines could not be loaded, and not that there are none, on a failure", async () => {
    installRoutes({ [UNMAPPED]: () => reply(500, { code: "internal_error", message: "x" }) });

    renderDialog();

    expect(await screen.findByText("No se pudieron cargar las líneas. Inténtalo de nuevo más tarde.")).toBeInTheDocument();
    expect(screen.queryByText("No hay líneas sin mapeo")).not.toBeInTheDocument();
  });

  it.each([[401, "unauthenticated"], [403, "forbidden"]])("reports a %i as fatal %s", async (status, kind) => {
    installRoutes({ [UNMAPPED]: () => reply(status, { code: "x", message: "x" }) });

    const props = renderDialog();

    await waitFor(() => expect(props.onFatal).toHaveBeenCalledWith(kind));
  });
});
