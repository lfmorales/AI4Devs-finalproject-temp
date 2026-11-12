import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { User } from "oidc-client-ts";

import CampaignsPage from "@/app/(authenticated)/campaigns/page";
import { AuthContext, type AuthContextValue } from "@/lib/auth/AuthContext";

// Mock getUserManager but NOT the API client - use real fetch
vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({
      id_token: "token",
      expired: false,
    } as User),
  }),
}));

describe("CampaignsPage 403 Forbidden", () => {
  let fetchMock: any;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://localhost/api";

    // Mock the global fetch
    fetchMock = vi.fn();
    global.fetch = fetchMock;

    vi.clearAllMocks();
  });

  afterEach(() => {
    delete process.env.NEXT_PUBLIC_API_URL;
  });

  it("displays AccessDeniedPage when API returns 403 forbidden with real fetch", async () => {
    const authValue: AuthContextValue = {
      session: { status: "authenticated", email: "user@example.com", bearerToken: "token" },
      signIn: vi.fn(),
      signOut: vi.fn(),
    };

    // Mock fetch to return 403 with missing_role error
    fetchMock.mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({
        code: "missing_role",
        message: "User lacks the required role",
      }),
    });

    render(
      <AuthContext.Provider value={authValue}>
        <CampaignsPage />
      </AuthContext.Provider>
    );

    // Should display AccessDeniedPage with "Acceso denegado" text
    await waitFor(() => {
      expect(screen.getByText(/acceso denegado/i)).toBeInTheDocument();
    });

    // Verify it's NOT showing a generic error message or empty table
    expect(screen.queryByText(/error al cargar las campañas/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/todavía no hay campañas/i)).not.toBeInTheDocument();
  });
});
