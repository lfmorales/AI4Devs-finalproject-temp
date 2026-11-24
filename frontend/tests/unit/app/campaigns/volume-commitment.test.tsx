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
    getUser: vi.fn().mockResolvedValue({ access_token: "t", expired: false } as unknown as User),
    removeUser: vi.fn(),
  }),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

// The fake masters list «Canal A» (id 1) and «Deal» (id 2).
const CANAL_A = "1";
const DEAL = "2";

const submit = () => fireEvent.click(screen.getByRole("button", { name: "Registrar campaña" }));
const commitmentOf = (index: number) => fieldNear(lineSection(index), /Tipo de volumen/) as HTMLSelectElement;
const shownLabel = (select: HTMLSelectElement) => select.selectedOptions[0]?.textContent;

async function formWithLine() {
  const api = installFakeApi({ preview: () => TWO_MONTH_PREVIEW, register: () => ({ status: 201, body: {} }) });
  await renderForm();
  fillCampaignHeader();
  fillLine(0);
  return api;
}

async function sentCommitments(api: Awaited<ReturnType<typeof formWithLine>>): Promise<unknown[]> {
  submit();
  await waitFor(() => expect(api.to("POST", "/campaigns")).toHaveLength(1));
  const lines = api.to("POST", "/campaigns")[0]!.body!.lines as Record<string, unknown>[];
  return lines.map((line) => line.volume_commitment);
}

describe("the volume commitment of a line", () => {
  it("is a selector of each line with «Compromiso» and «Objetivo»", async () => {
    await formWithLine();

    const select = commitmentOf(0);
    expect(within(select).getAllByRole("option").map((option) => option.textContent)).toEqual(["Compromiso", "Objetivo"]);
  });

  it("proposes «Objetivo» when the channel is Deal and «Compromiso» for any other channel", async () => {
    await formWithLine();

    setValue(fieldNear(lineSection(0), /Canal/), DEAL);
    expect(shownLabel(commitmentOf(0))).toBe("Objetivo");

    setValue(fieldNear(lineSection(0), /Canal/), CANAL_A);
    expect(shownLabel(commitmentOf(0))).toBe("Compromiso");
  });

  it("keeps the user's choice when the channel changes afterwards", async () => {
    await formWithLine();
    setValue(fieldNear(lineSection(0), /Canal/), DEAL);

    setValue(commitmentOf(0), "committed");
    setValue(fieldNear(lineSection(0), /Canal/), CANAL_A);
    setValue(fieldNear(lineSection(0), /Canal/), DEAL);

    expect(shownLabel(commitmentOf(0))).toBe("Compromiso");
  });

  it("sends the proposal when the user leaves it: target for a Deal line", async () => {
    const api = await formWithLine();
    setValue(fieldNear(lineSection(0), /Canal/), DEAL);

    expect(await sentCommitments(api)).toEqual(["target"]);
  });

  it("sends what the user chose when the user changes the proposal", async () => {
    const api = await formWithLine();
    setValue(fieldNear(lineSection(0), /Canal/), DEAL);

    setValue(commitmentOf(0), "committed");

    expect(shownLabel(commitmentOf(0))).toBe("Compromiso");
    expect(await sentCommitments(api)).toEqual(["committed"]);
  });

  it("sends committed for a line on another channel, and target if the user chooses it", async () => {
    const api = await formWithLine();

    setValue(commitmentOf(0), "target");

    expect(shownLabel(commitmentOf(0))).toBe("Objetivo");
    expect(await sentCommitments(api)).toEqual(["target"]);
  });

  it("gives every added line its own selector and proposal", async () => {
    const api = await formWithLine();
    fireEvent.click(screen.getByRole("button", { name: /Añadir línea/ }));
    fillLine(1);

    setValue(fieldNear(lineSection(1), /Canal/), DEAL);

    expect([shownLabel(commitmentOf(0)), shownLabel(commitmentOf(1))]).toEqual(["Compromiso", "Objetivo"]);
    expect(await sentCommitments(api)).toEqual(["committed", "target"]);
  });
});
