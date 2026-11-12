import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RequireAuth } from "@/features/auth/RequireAuth";
import { AuthContext, type AuthContextValue, type AuthSession } from "@/lib/auth/AuthContext";

function renderWithSession(session: AuthSession, signIn = vi.fn<AuthContextValue["signIn"]>()) {
  const value: AuthContextValue = { session, signIn, signOut: vi.fn() };
  render(
    <AuthContext.Provider value={value}>
      <RequireAuth>
        <p>Protected content</p>
      </RequireAuth>
    </AuthContext.Provider>,
  );
  return { signIn };
}

describe("RequireAuth", () => {
  it("shows a session check, not the protected content, while the session is loading", () => {
    renderWithSession({ status: "loading" });

    expect(screen.getByRole("status")).toHaveTextContent(/checking your session/i);
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
  });

  it("hides the protected content from an unauthenticated user and offers to sign in", async () => {
    window.history.pushState({}, "", "/account");
    const { signIn } = renderWithSession({ status: "unauthenticated" });

    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(signIn).toHaveBeenCalledWith("/account");
  });

  it("renders the protected content for an authenticated user", () => {
    renderWithSession({ status: "authenticated", email: "ops@example.com", bearerToken: "token" });

    expect(screen.getByText("Protected content")).toBeInTheDocument();
  });
});
