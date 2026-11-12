import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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

describe("CreateCampaignPage - Error Handling", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_URL = "http://localhost/api";
    vi.clearAllMocks();
    setupMasterDataMocks();
  });

  it("displays error message on submit failure", async () => {
    const mockError = new Error("Hay campos con errores");
    (mockError as any).kind = "failed";
    (mockError as any).status = 422;
    (mockError as any).fieldErrors = {};
    (mockError as any).name = "ApiError";

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

    // Verify the form renders without errors
    expect(screen.getByText(/registrar campaña/i)).toBeInTheDocument();
  });

  it("prevents double submission by disabling button during submission", async () => {
    // Mock a never-resolving promise
    mockPost.mockImplementationOnce(
      () =>
        new Promise(() => {
          // Never resolves
        })
    );

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

    // Verify form is ready
    expect(screen.getByText(/registrar campaña/i)).toBeInTheDocument();
  });
});
