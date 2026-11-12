import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "@/lib/auth/AuthContext";
import { AuthProvider } from "@/lib/auth/AuthProvider";

const getUser = vi.fn();
const removeUser = vi.fn();
const signoutRedirect = vi.fn();

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser,
    removeUser,
    signoutRedirect,
    events: {
      addUserLoaded: () => {},
      removeUserLoaded: () => {},
      addUserUnloaded: () => {},
      removeUserUnloaded: () => {},
      addSilentRenewError: () => {},
      removeSilentRenewError: () => {},
    },
  }),
  getLogoutUrl: () => "https://cognito.example/logout",
}));

function Probe() {
  const { session, signOut } = useAuth();
  if (session.status === "loading") return <div>Loading</div>;
  if (session.status !== "authenticated") return <div>{session.status}</div>;
  return (
    <div>
      <span>email:{session.email}</span>
      <span>bearer:{session.bearerToken}</span>
      <button onClick={() => void signOut()}>Sign out</button>
    </div>
  );
}

const assign = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(window, "location", { value: { assign }, configurable: true });
});
afterEach(() => vi.unstubAllEnvs());

function validUser(fields: Record<string, unknown>) {
  return { expired: false, id_token: "token-de-identidad", access_token: "token-de-acceso", profile: {}, ...fields };
}

describe("AuthProvider with entra", () => {
  beforeEach(() => vi.stubEnv("NEXT_PUBLIC_AUTH_PROVIDER", "entra"));

  it("keeps the access token as the token to send", async () => {
    getUser.mockResolvedValue(validUser({ profile: { email: "a@example.com" } }));

    render(<AuthProvider><Probe /></AuthProvider>);

    expect(await screen.findByText("bearer:token-de-acceso")).toBeInTheDocument();
  });

  it("does not consider valid a session without access token", async () => {
    getUser.mockResolvedValue(validUser({ access_token: undefined }));

    render(<AuthProvider><Probe /></AuthProvider>);

    expect(await screen.findByText("unauthenticated")).toBeInTheDocument();
  });

  it("shows preferred_username when there is no email, and then the name, and never fails", async () => {
    getUser.mockResolvedValue(validUser({ profile: { preferred_username: "b@example.com", name: "c" } }));
    const first = render(<AuthProvider><Probe /></AuthProvider>);
    expect(await screen.findByText("email:b@example.com")).toBeInTheDocument();
    first.unmount();

    getUser.mockResolvedValue(validUser({ profile: { name: "Nombre de Prueba" } }));
    const second = render(<AuthProvider><Probe /></AuthProvider>);
    expect(await screen.findByText("email:Nombre de Prueba")).toBeInTheDocument();
    second.unmount();

    getUser.mockResolvedValue(validUser({ profile: {} }));
    render(<AuthProvider><Probe /></AuthProvider>);
    expect(await screen.findByText("email:")).toBeInTheDocument();
  });

  it("signs out through signoutRedirect and not through the Cognito logout URL", async () => {
    getUser.mockResolvedValue(validUser({ profile: { email: "a@example.com" } }));
    render(<AuthProvider><Probe /></AuthProvider>);

    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(signoutRedirect).toHaveBeenCalledTimes(1));
    expect(assign).not.toHaveBeenCalled();
  });
});

describe("AuthProvider with cognito", () => {
  it("keeps the identity token as the token to send", async () => {
    getUser.mockResolvedValue(validUser({ profile: { email: "a@example.com" } }));

    render(<AuthProvider><Probe /></AuthProvider>);

    expect(await screen.findByText("bearer:token-de-identidad")).toBeInTheDocument();
  });

  it("does not consider valid a session without identity token, whatever the access token", async () => {
    getUser.mockResolvedValue(validUser({ id_token: undefined }));

    render(<AuthProvider><Probe /></AuthProvider>);

    expect(await screen.findByText("unauthenticated")).toBeInTheDocument();
  });

  it("signs out as today: removes the user and goes to the hosted UI logout URL", async () => {
    getUser.mockResolvedValue(validUser({ profile: { email: "a@example.com" } }));
    render(<AuthProvider><Probe /></AuthProvider>);

    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://cognito.example/logout"));
    expect(removeUser).toHaveBeenCalledTimes(1);
    expect(signoutRedirect).not.toHaveBeenCalled();
  });
});
