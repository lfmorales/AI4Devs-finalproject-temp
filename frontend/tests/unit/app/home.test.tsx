import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import HomePage from "@/app/page";
import { AuthContext, type AuthContextValue } from "@/lib/auth/AuthContext";

// Mock useRouter
const mockPush = vi.fn();
const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
  }),
}));

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

  it("redirects to campaigns when authenticated", () => {
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

    expect(mockReplace).toHaveBeenCalledWith("/campaigns");
  });
});
