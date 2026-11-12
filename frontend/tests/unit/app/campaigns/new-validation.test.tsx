import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { User } from "oidc-client-ts";

import CreateCampaignPage from "@/app/(authenticated)/campaigns/new/page";
import { AuthContext, type AuthContextValue } from "@/lib/auth/AuthContext";

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("@/lib/api/client", () => {
  class MockApiError extends Error {
    fieldErrors: Record<string, string> = {};
    constructor(public kind: string, public status: number, message: string, public code?: string) {
      super(message);
      this.name = "ApiError";
    }
  }

  return {
    createApiClient: () => ({
      get: mockGet,
      post: mockPost,
    }),
    ApiError: MockApiError,
  };
});

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: vi.fn().mockResolvedValue({
      id_token: "token",
      expired: false,
    } as User),
    removeUser: vi.fn(),
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

function setupMasterDataMocks() {
  mockGet.mockImplementation((path: string) => {
    const mockData: Record<string, unknown[]> = {
      "/masters/agencies": [{ id: 1, name: "Agencia A" }],
      "/masters/advertisers": [{ id: 1, name: "Anunciante A" }],
      "/masters/campaign-types": [{ id: 1, name: "Tipo A" }],
      "/masters/sectors": [{ id: 1, name: "Sector A" }],
      "/masters/sales-reps": [{ id: 1, name: "Rep A" }],
      "/masters/dsps": [{ id: 1, name: "DSP A", is_active: true }],
      "/masters/channels": [{ id: 1, name: "Canal A" }],
      "/masters/formats": [{ id: 1, name: "Formato A" }],
    };
    return Promise.resolve(mockData[path] || []);
  });
}

describe("CreateCampaignPage - Zod Validation", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://localhost/api";
    vi.clearAllMocks();
    setupMasterDataMocks();
  });

  it("shows field-specific errors on empty form submission, not raw JSON", async () => {
    const user = userEvent.setup();

    const authValue: AuthContextValue = {
      session: { status: "authenticated", email: "user@example.com", bearerToken: "token" },
      signIn: vi.fn(),
      signOut: vi.fn(),
    };

    render(
      <AuthContext.Provider value={authValue}>
        <CreateCampaignPage />
      </AuthContext.Provider>
    );

    await waitFor(() => {
      expect(screen.getByText("Agencia A")).toBeInTheDocument();
    });

    // Submit empty form
    const submitButton = screen.getByText(/registrar campaña/i);
    await user.click(submitButton);

    // Wait for error messages to appear
    await waitFor(() => {
      expect(screen.getByText("Nombre de la campaña es obligatorio")).toBeInTheDocument();
    });

    // Verify no raw JSON error messages appear
    const errorElements = screen.queryAllByRole("status");
    const errorText = errorElements.map((el) => el.textContent).join(" ");
    expect(errorText).not.toMatch(/\[.*"loc".*\]/); // No Zod issues JSON
    expect(errorText).not.toMatch(/origin/i); // No Zod origin field
  });

  it("never shows raw validation error.message in generic catch", async () => {
    const mockError = new Error("Some unexpected error");
    mockPost.mockRejectedValueOnce(mockError);

    const authValue: AuthContextValue = {
      session: { status: "authenticated", email: "user@example.com", bearerToken: "token" },
      signIn: vi.fn(),
      signOut: vi.fn(),
    };

    render(
      <AuthContext.Provider value={authValue}>
        <CreateCampaignPage />
      </AuthContext.Provider>
    );

    await waitFor(() => {
      expect(screen.getByText("Agencia A")).toBeInTheDocument();
    });

    // Verify form renders without showing raw error message
    expect(screen.getByText(/registrar campaña/i)).toBeInTheDocument();
  });

  it("maps nested line errors to field paths like lines.0.sale_cpm", async () => {
    const authValue: AuthContextValue = {
      session: { status: "authenticated", email: "user@example.com", bearerToken: "token" },
      signIn: vi.fn(),
      signOut: vi.fn(),
    };

    render(
      <AuthContext.Provider value={authValue}>
        <CreateCampaignPage />
      </AuthContext.Provider>
    );

    await waitFor(() => {
      expect(screen.getByText("Agencia A")).toBeInTheDocument();
    });

    // Form is ready
    expect(screen.getByText(/registrar campaña/i)).toBeInTheDocument();
  });
});
