"use client";

import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/lib/auth/AuthContext";
import { createApiClient, type ApiClient, type ApiError } from "./client";

/** What a page that loads one resource can be showing. Each state is distinct from the others. */
export type ApiCallState<TData> =
  | { status: "loading" }
  | { status: "ready"; data: TData }
  | { status: "error" }
  | { status: "forbidden" }
  | { status: "unauthenticated" };

/**
 * Loads a resource through the API client once the session is authenticated, and again whenever `key` changes.
 * A 401 and a 403 become their own states so the page can show the matching screen.
 */
export function useApiCall<TData>(
  key: string,
  load: (client: ApiClient) => Promise<TData>,
): { state: ApiCallState<TData>; setData: (data: TData) => void } {
  const { session } = useAuth();
  const [state, setState] = useState<ApiCallState<TData>>({ status: "loading" });
  const latestLoad = useRef(load);
  latestLoad.current = load;
  const authenticated = session.status === "authenticated";

  useEffect(() => {
    if (!authenticated) return;
    let cancelled = false;
    setState({ status: "loading" });

    async function run() {
      try {
        const baseUrl = process.env.NEXT_PUBLIC_API_URL;
        if (!baseUrl) throw new Error("API URL not configured");
        const data = await latestLoad.current(createApiClient({ baseUrl }));
        if (!cancelled) setState({ status: "ready", data });
      } catch (caught) {
        if (cancelled) return;
        const kind = (caught as Partial<ApiError>).kind;
        if (kind === "unauthenticated") setState({ status: "unauthenticated" });
        else if (kind === "forbidden") setState({ status: "forbidden" });
        else setState({ status: "error" });
      }
    }

    void run();
    return () => {
      cancelled = true;
    };
  }, [authenticated, key]);

  return { state, setData: (data) => setState({ status: "ready", data }) };
}
