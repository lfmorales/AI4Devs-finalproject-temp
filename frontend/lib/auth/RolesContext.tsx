"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import { useApiCall } from "@/lib/api/useApiCall";
import { ROLES, type Role } from "./navigation";

/** What the navigation knows about the user's roles. They live only in memory, for as long as the provider is mounted. */
export type RolesState =
  | { status: "loading" }
  | { status: "ready"; roles: readonly Role[] }
  | { status: "no_profile" }
  | { status: "error"; retry: () => void };

interface OwnRolesResponse {
  roles: string[];
}

/** Without a provider the roles are not known, so nothing that depends on a role is shown. */
export const RolesContext = createContext<RolesState>({ status: "loading" });

/** Asks GET /users/me once the session is authenticated; unmounting it, as signing out does, forgets the roles. */
export function RolesProvider({ children }: { children: ReactNode }) {
  const [attempt, setAttempt] = useState(0);
  const { state } = useApiCall<OwnRolesResponse>(`roles-${attempt}`, (client) => client.get<OwnRolesResponse>("/users/me"));

  const value = useMemo<RolesState>(() => {
    if (state.status === "ready") {
      const roles = ROLES.filter((role) => state.data.roles.includes(role));
      return roles.length > 0 ? { status: "ready", roles } : { status: "no_profile" };
    }
    if (state.status === "forbidden") return { status: "no_profile" };
    if (state.status === "error") return { status: "error", retry: () => setAttempt((current) => current + 1) };
    // A 401 ends the session, which the layout answers with "Sesión caducada"; until then nothing is shown.
    return { status: "loading" };
  }, [state]);

  return <RolesContext.Provider value={value}>{children}</RolesContext.Provider>;
}

export function useRoles(): RolesState {
  return useContext(RolesContext);
}

/** Whether the roles are loaded and the user holds at least one of the given ones. */
export function useHasAnyRole(...accepted: Role[]): boolean {
  const state = useRoles();
  return state.status === "ready" && accepted.some((role) => state.roles.includes(role));
}
