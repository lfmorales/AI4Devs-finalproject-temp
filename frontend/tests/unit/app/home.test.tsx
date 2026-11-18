import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import HomePage from "@/app/page";
import { AuthContext, type AuthContextValue } from "@/lib/auth/AuthContext";
import { installRoutes, rolesRoutes } from "../../helpers/api-pages";

// Mock useRouter
const mockPush = vi.fn();
const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
  }),
}));

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({ getUser: vi.fn().mockResolvedValue({ access_token: "token", expired: false }), removeUser: vi.fn() }),
}));

afterEach(() => vi.unstubAllGlobals());

describe("HomePage", () => {
  it("shows loading indicator when session is loading", () => {
    const authValue: AuthContextValue = {
      session: { status: "loading" },
      signIn: vi.fn(),
      signOut: vi.fn(),
    };

    render(
      <AuthContext.Provider value={authValue}>
        <HomePage />
      </AuthContext.Provider>
    );

    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows sign in button when unauthenticated", async () => {
    const mockSignIn = vi.fn();
    const authValue: AuthContextValue = {
      session: { status: "unauthenticated" },
      signIn: mockSignIn,
      signOut: vi.fn(),
    };

    const user = userEvent.setup();

    render(
      <AuthContext.Provider value={authValue}>
        <HomePage />
      </AuthContext.Provider>
    );

    const signInButton = screen.getByRole("button", { name: /iniciar sesión/i });
    expect(signInButton).toBeInTheDocument();

    await user.click(signInButton);
    expect(mockSignIn).toHaveBeenCalledWith("/campaigns");
  });

  it("redirects to campaigns when authenticated and holding operations", async () => {
    installRoutes(rolesRoutes(["operations"]));
    const authValue: AuthContextValue = {
      session: { status: "authenticated", email: "user@example.com", bearerToken: "token" },
      signIn: vi.fn(),
      signOut: vi.fn(),
    };

    render(
      <AuthContext.Provider value={authValue}>
        <HomePage />
      </AuthContext.Provider>
    );

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/campaigns"));
  });
});
