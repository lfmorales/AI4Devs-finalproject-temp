import { createApiClient, type ApiClient } from "./client";

/** The API client of a page action (a click, a form): the same client `useApiCall` builds for a read. */
export function browserApiClient(): ApiClient {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!baseUrl) throw new Error("API URL not configured");
  return createApiClient({ baseUrl });
}
