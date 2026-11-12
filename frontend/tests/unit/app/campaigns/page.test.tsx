import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { User } from "oidc-client-ts";

import CampaignsPage from "@/app/(authenticated)/campaigns/page";
import { AuthContext, type AuthContextValue } from "@/lib/auth/AuthContext";

// Mock createApiClient
const mockGet = vi.fn();
vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({
    get: mockGet,
    post: vi.fn(),
  }),
}));

// Mock getUserManager
vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({
      id_token: "token",
      expired: false,
    } as User),
  }),
}));

describe("CampaignsPage", () => {
  beforeEach(() => {
    // Set API URL for tests
    process.env.NEXT_PUBLIC_API_URL = "http://localhost/api";
    vi.clearAllMocks();
  });

  afterEach(() => {
    delete process.env.NEXT_PUBLIC_API_URL;
  });

  it("displays loading state initially", () => {
    mockGet.mockImplementation(() => new Promise(() => {})); // Never resolves

    const authValue: AuthContextValue = {
      session: { status: "authenticated", email: "user@example.com", bearerToken: "token" },
      signIn: vi.fn(),
      signOut: vi.fn(),
    };

    render(
      <AuthContext.Provider value={authValue}>
        <CampaignsPage />
      </AuthContext.Provider>
    );

    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("displays campaign table with data when loaded", async () => {
    const campaigns = [
      {
        id: 1,
        name: "CAMP-001",
        display_name: "Campaign One",
        agency_id: 1,
        advertiser_id: 1,
        status: "active",
        start_date: "2026-01-01",
        end_date: "2026-03-31",
      },
      {
        id: 2,
        name: "CAMP-002",
        display_name: "Campaign Two",
        agency_id: 2,
        advertiser_id: 2,
        status: "paused",
        start_date: "2026-02-01",
        end_date: "2026-04-30",
      },
    ];

    mockGet.mockResolvedValue(campaigns);

    const authValue: AuthContextValue = {
      session: { status: "authenticated", email: "user@example.com", bearerToken: "token" },
      signIn: vi.fn(),
      signOut: vi.fn(),
    };

    render(
      <AuthContext.Provider value={authValue}>
        <CampaignsPage />
      </AuthContext.Provider>
    );

    await waitFor(() => {
      expect(screen.getByText("CAMP-001")).toBeInTheDocument();
    });

    expect(screen.getByText("Campaign One")).toBeInTheDocument();
    expect(screen.getByText("CAMP-002")).toBeInTheDocument();
    expect(screen.getByText("Campaign Two")).toBeInTheDocument();
  });

  it("displays empty state when no campaigns exist", async () => {
    mockGet.mockResolvedValue([]);

    const authValue: AuthContextValue = {
      session: { status: "authenticated", email: "user@example.com", bearerToken: "token" },
      signIn: vi.fn(),
      signOut: vi.fn(),
    };

    render(
      <AuthContext.Provider value={authValue}>
        <CampaignsPage />
      </AuthContext.Provider>
    );

    await waitFor(() => {
      expect(screen.getByText(/todavía no hay campañas/i)).toBeInTheDocument();
    });
  });

  it("displays error state when request fails", async () => {
    mockGet.mockRejectedValue(new Error("Failed to load campaigns"));

    const authValue: AuthContextValue = {
      session: { status: "authenticated", email: "user@example.com", bearerToken: "token" },
      signIn: vi.fn(),
      signOut: vi.fn(),
    };

    render(
      <AuthContext.Provider value={authValue}>
        <CampaignsPage />
      </AuthContext.Provider>
    );

    await waitFor(() => {
      expect(screen.getByText(/error al cargar las campañas/i)).toBeInTheDocument();
    });
  });

  it("displays AccessDeniedPage when receiving 403 forbidden response", async () => {
    // Create a mock ApiError with the properties that would come from a 403 response
    const forbiddenError = new Error("User lacks the required role");
    Object.assign(forbiddenError, {
      kind: "forbidden",
      status: 403,
      code: "missing_role",
      fieldErrors: {},
    });
    mockGet.mockRejectedValue(forbiddenError);

    const authValue: AuthContextValue = {
      session: { status: "authenticated", email: "user@example.com", bearerToken: "token" },
      signIn: vi.fn(),
      signOut: vi.fn(),
    };

    render(
      <AuthContext.Provider value={authValue}>
        <CampaignsPage />
      </AuthContext.Provider>
    );

    await waitFor(() => {
      expect(screen.getByText(/acceso denegado/i)).toBeInTheDocument();
    });

    // Verify it's NOT showing a generic error message or empty table
    expect(screen.queryByText(/error al cargar las campañas/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/todavía no hay campañas/i)).not.toBeInTheDocument();
  });
});
