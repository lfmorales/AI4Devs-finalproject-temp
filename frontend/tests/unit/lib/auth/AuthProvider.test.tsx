import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { User } from "oidc-client-ts";

import { AuthProvider } from "@/lib/auth/AuthProvider";
import { useAuth } from "@/lib/auth/AuthContext";

// Mock getUserManager
const mockGetUser = vi.fn();
const mockAddUserLoaded = vi.fn();
const mockAddUserUnloaded = vi.fn();
const mockAddSilentRenewError = vi.fn();
const mockRemoveUserLoaded = vi.fn();
const mockRemoveUserUnloaded = vi.fn();
const mockRemoveSilentRenewError = vi.fn();
const mockRemoveUser = vi.fn();
const mockSigninRedirect = vi.fn();
const mockSignoutRedirect = vi.fn();

const mockEvents = {
  addUserLoaded: mockAddUserLoaded,
  addUserUnloaded: mockAddUserUnloaded,
  addSilentRenewError: mockAddSilentRenewError,
  removeUserLoaded: mockRemoveUserLoaded,
  removeUserUnloaded: mockRemoveUserUnloaded,
  removeSilentRenewError: mockRemoveSilentRenewError,
};

vi.mock("@/lib/auth/user-manager", () => ({
  getUserManager: () => ({
    getUser: mockGetUser,
    events: mockEvents,
    removeUser: mockRemoveUser,
    signinRedirect: mockSigninRedirect,
    signoutRedirect: mockSignoutRedirect,
  }),
}));

function TestComponent() {
  const { session } = useAuth();
  if (session.status === "loading") return <div>Loading</div>;
  if (session.status === "unauthenticated") return <div>Unauthenticated</div>;
  if (session.status === "session_expired") return <div>SessionExpired</div>;
  if (session.status === "authenticated") return <div>Authenticated: {session.email}</div>;
  return null;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetUser.mockResolvedValue(null);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AuthProvider session expiration", () => {
  it("transitions to session_expired when userUnloaded fires from authenticated state", async () => {
    const user: User = {
      access_token: "token",
      profile: { email: "test@example.com" },
      expired: false,
    } as User;

    mockGetUser.mockResolvedValue(user);

    mockAddUserUnloaded.mockImplementation((callback: () => void) => {
      // Capture for later invocation
      (mockAddUserUnloaded as any).capturedCallback = callback;
    });

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    // Initially loading, then authenticated
    await waitFor(() => expect(screen.queryByText("Authenticated: test@example.com")).toBeInTheDocument());

    // Simulate userUnloaded event
    const userUnloadedCallback = (mockAddUserUnloaded as any).capturedCallback as (() => void);
    userUnloadedCallback();

    // Should transition to session_expired (not unauthenticated)
    await waitFor(() => expect(screen.getByText("SessionExpired")).toBeInTheDocument());
  });

  it("stays unauthenticated when userUnloaded fires from unauthenticated state", async () => {
    mockGetUser.mockResolvedValue(null);

    mockAddUserUnloaded.mockImplementation((callback: () => void) => {
      // Capture for later invocation
      (mockAddUserUnloaded as any).capturedCallback = callback;
    });

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    // Initially unauthenticated
    await waitFor(() => expect(screen.getByText("Unauthenticated")).toBeInTheDocument());

    // Simulate userUnloaded event
    const userUnloadedCallback = (mockAddUserUnloaded as any).capturedCallback as (() => void);
    userUnloadedCallback();

    // Should remain unauthenticated (not transition to session_expired)
    expect(screen.getByText("Unauthenticated")).toBeInTheDocument();
  });

  it("goes directly to unauthenticated when signOut is called voluntarily", async () => {
    const user: User = {
      access_token: "token",
      profile: { email: "test@example.com" },
      expired: false,
    } as User;

    mockGetUser.mockResolvedValue(user);

    const signOutRef: { current?: () => Promise<void> } = {};

    function TestComponentWithSignOut() {
      const { session, signOut } = useAuth();
      signOutRef.current = signOut;
      if (session.status === "loading") return <div>Loading</div>;
      if (session.status === "unauthenticated") return <div>Unauthenticated</div>;
      if (session.status === "session_expired") return <div>SessionExpired</div>;
      if (session.status === "authenticated") return <div>Authenticated: {session.email}</div>;
      return null;
    }

    render(
      <AuthProvider>
        <TestComponentWithSignOut />
      </AuthProvider>
    );

    // Initially authenticated
    await waitFor(() => expect(screen.queryByText("Authenticated: test@example.com")).toBeInTheDocument());

    // Call signOut voluntarily
    if (signOutRef.current) {
      await signOutRef.current();
    }

    // Should go to unauthenticated (not session_expired) because it was voluntary; oidc-client-ts's signoutRedirect
    // removes the user itself before it leaves for Entra.
    expect(mockSignoutRedirect).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.getByText("Unauthenticated")).toBeInTheDocument());
  });
});
