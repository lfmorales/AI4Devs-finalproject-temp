/**
 * Helpers for tests of the new-campaign form that use the real API client over a simulated fetch.
 * The test file must mock "@/lib/auth/user-manager" and "next/navigation" itself (vi.mock is per file).
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";

import { CreateCampaignForm } from "@/features/campaigns/CreateCampaignForm";
import { AuthContext, type AuthContextValue } from "@/lib/auth/AuthContext";

export const API_URL = "http://localhost/api";

export interface RecordedRequest {
  method: string;
  path: string;
  body: Record<string, unknown> | undefined;
}

export interface FakeReply {
  status: number;
  body: unknown;
}

export interface FakeApi {
  requests: RecordedRequest[];
  /** The requests of one method and path, in order. */
  to(method: string, path: string): RecordedRequest[];
}

export type Handler = (body: Record<string, any>) => FakeReply;

const MASTERS: Record<string, unknown[]> = {
  "/masters/agencies": [{ id: 1, name: "Agencia A" }],
  "/masters/advertisers": [{ id: 1, name: "Anunciante A" }],
  "/masters/campaign-types": [{ id: 1, name: "Tipo A" }],
  "/masters/sectors": [{ id: 1, name: "Sector A" }],
  "/masters/sales-reps": [{ id: 1, name: "Rep A" }],
  "/masters/dsps": [{ id: 1, name: "DSP A", is_active: true }],
  "/masters/channels": [{ id: 1, name: "Canal A" }],
  "/masters/formats": [{ id: 1, name: "Formato A" }],
};

/** Replace fetch with a router over the backend's paths. Unhandled POSTs fail the test loudly. */
export function installFakeApi(handlers: { preview?: Handler; register?: Handler } = {}): FakeApi {
  const requests: RecordedRequest[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const path = url.replace(API_URL, "");
    const method = init?.method ?? "GET";
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : undefined;
    requests.push({ method, path, body });

    let reply: FakeReply | undefined;
    if (method === "GET" && path in MASTERS) reply = { status: 200, body: MASTERS[path] };
    if (method === "POST" && path === "/flights/preview") reply = handlers.preview?.(body ?? {});
    if (method === "POST" && path === "/campaigns") reply = handlers.register?.(body ?? {});
    if (!reply) throw new Error(`Unhandled request ${method} ${path}`);
    return new Response(JSON.stringify(reply.body), { status: reply.status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return {
    requests,
    to: (method, path) => requests.filter((r) => r.method === method && r.path === path),
  };
}

export function flight(year: number, month: number, start: string, end: string, volume: number) {
  return { period_year: year, period_month: month, flight_start: start, flight_end: end, contracted_impressions: volume };
}

/** A preview of Aug 1 to Sep 30 split 3100 / 3000, the answer most tests need. */
export const TWO_MONTH_PREVIEW: FakeReply = {
  status: 200,
  body: {
    start_date: "2026-08-01",
    end_date: "2026-09-30",
    flights: [flight(2026, 8, "2026-08-01", "2026-08-31", 3100), flight(2026, 9, "2026-09-01", "2026-09-30", 3000)],
  },
};

export async function renderForm(onAuthError?: (kind: "unauthenticated" | "forbidden") => void) {
  process.env.NEXT_PUBLIC_API_URL = API_URL;
  const auth: AuthContextValue = {
    session: { status: "authenticated", email: "user@example.com", idToken: "token" },
    signIn: vi.fn(),
    signOut: vi.fn(),
  };
  const view = render(
    <AuthContext.Provider value={auth}>
      <CreateCampaignForm onAuthError={onAuthError} />
    </AuthContext.Provider>,
  );
  await waitFor(() => expect(screen.getByText("Agencia A")).toBeInTheDocument());
  return view;
}

/** The input or select that sits in the same block as a label with this text. */
export function fieldNear(scope: HTMLElement | typeof screen, labelText: string | RegExp): HTMLInputElement | HTMLSelectElement {
  const queries = "getByText" in scope ? scope : within(scope);
  const label = queries.getByText(labelText, { selector: "label" });
  const field = label.parentElement?.querySelector("input, select");
  if (!field) throw new Error(`No field next to ${String(labelText)}`);
  return field as HTMLInputElement | HTMLSelectElement;
}

export function setValue(field: HTMLElement, value: string) {
  fireEvent.change(field, { target: { value } });
}

export function lineSection(index: number): HTMLElement {
  const heading = screen.getByRole("heading", { name: `Línea ${index + 1}` });
  return heading.parentElement!.parentElement!;
}

export function fillCampaignHeader(dates = { start: "2026-08-01", end: "2026-09-30" }) {
  setValue(fieldNear(screen, /Nombre de la campaña/), "Campaña de prueba");
  setValue(fieldNear(screen, /Nombre mostrado/), "Campaña");
  setValue(fieldNear(screen, /Agencia/), "1");
  setValue(fieldNear(screen, /Anunciante/), "1");
  setValue(fieldNear(screen, /Tipo de campaña/), "1");
  setValue(fieldNear(screen, /Sector/), "1");
  setValue(fieldNear(screen, /Comercial/), "1");
  setValue(fieldNear(screen, /Fecha de inicio \*/), dates.start);
  setValue(fieldNear(screen, /Fecha de fin \*/), dates.end);
  setValue(fieldNear(screen, /Referencia de orden/), "PO-1");
  setValue(fieldNear(screen, /Fecha de recepción/), "2026-07-01");
}

export function fillLine(index: number, total = "6100") {
  const line = lineSection(index);
  setValue(fieldNear(line, /DSP/), "1");
  setValue(fieldNear(line, /Canal/), "1");
  setValue(fieldNear(line, /Formato/), "1");
  setValue(fieldNear(line, /Alcance/), "national");
  setValue(fieldNear(line, /Descripción del mercado/), "Nacional");
  setValue(fieldNear(line, /Impresiones contratadas/), total);
  setValue(fieldNear(line, /CPM/), "5.00");
}
