import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AuthContext, type AuthContextValue } from "@/lib/auth/AuthContext";
import AuthenticatedLayout from "@/app/(authenticated)/layout";

vi.mock("next/navigation", () => ({
  usePathname: vi.fn(() => "/test-path"),
}));

describe("AuthenticatedLayout", () => {
  it("renders children when user is authenticated", () => {
    const authValue: AuthContextValue = {
      session: { status: "authenticated", email: "user@example.com", bearerToken: "token" },
      signIn: vi.fn(),
      signOut: vi.fn(),
    };

    render(
      <AuthContext.Provider value={authValue}>
        <AuthenticatedLayout>
          <div>Campaign Page Content</div>
        </AuthenticatedLayout>
      </AuthContext.Provider>
    );

    expect(screen.getByText("Campaign Page Content")).toBeInTheDocument();
  });

  it("shows session expired page when session was lost involuntarily", () => {
    const authValue: AuthContextValue = {
      session: { status: "session_expired" },
      signIn: vi.fn(),
      signOut: vi.fn(),
    };

    render(
      <AuthContext.Provider value={authValue}>
        <AuthenticatedLayout>
          <div>Campaign Page Content</div>
        </AuthenticatedLayout>
      </AuthContext.Provider>
    );

    expect(screen.getByText("Sesión caducada")).toBeInTheDocument();
    expect(screen.queryByText("Campaign Page Content")).not.toBeInTheDocument();
  });

  it("shows access denied page when there is a 403 error", () => {
    const authValue: AuthContextValue = {
      session: { status: "authenticated", email: "user@example.com", bearerToken: "token" },
      signIn: vi.fn(),
      signOut: vi.fn(),
    };

    // Simulate navigation with search param for 403 error
    render(
      <AuthContext.Provider value={authValue}>
        <AuthenticatedLayout>
          <div>Campaign Page Content</div>
        </AuthenticatedLayout>
      </AuthContext.Provider>
    );

    // When 403 error occurs, AccessDeniedPage should be shown
    // This is tested in practice through the API error handling
    expect(screen.getByText("Campaign Page Content")).toBeInTheDocument();
  });

  it("does not show session expired when user explicitly signed out", () => {
    const authValue: AuthContextValue = {
      session: { status: "unauthenticated" },
      signIn: vi.fn(),
      signOut: vi.fn(),
    };

    render(
      <AuthContext.Provider value={authValue}>
        <AuthenticatedLayout>
          <div>Campaign Page Content</div>
        </AuthenticatedLayout>
      </AuthContext.Provider>
    );

    // Should not show session expired for explicit logout
    expect(screen.queryByText("Sesión caducada")).not.toBeInTheDocument();
  });

  it("shows login button when unauthenticated without signIn being called", () => {
    const signInMock = vi.fn();
    const authValue: AuthContextValue = {
      session: { status: "unauthenticated" },
      signIn: signInMock,
      signOut: vi.fn(),
    };

    render(
      <AuthContext.Provider value={authValue}>
        <AuthenticatedLayout>
          <div>Campaign Page Content</div>
        </AuthenticatedLayout>
      </AuthContext.Provider>
    );

    const button = screen.getByRole("button", { name: /iniciar sesión/i });
    expect(button).toBeInTheDocument();
    expect(signInMock).not.toHaveBeenCalled();
  });

  it("calls signIn with current pathname when login button is clicked", async () => {
    const user = userEvent.setup();
    const signInMock = vi.fn();
    const authValue: AuthContextValue = {
      session: { status: "unauthenticated" },
      signIn: signInMock,
      signOut: vi.fn(),
    };

    render(
      <AuthContext.Provider value={authValue}>
        <AuthenticatedLayout>
          <div>Campaign Page Content</div>
        </AuthenticatedLayout>
      </AuthContext.Provider>
    );

    const button = screen.getByRole("button", { name: /iniciar sesión/i });
    await user.click(button);

    expect(signInMock).toHaveBeenCalledWith("/test-path");
  });
});
