import { getUserManager } from "@/lib/auth/user-manager";

/** The three failure cases the UI handles differently: re-authenticate, explain, or retry. */
export type ApiErrorKind = "unauthenticated" | "forbidden" | "failed";

export interface ValidationError {
  type: string;
  loc: (string | number)[];
  msg: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
}

export interface ApiErrorResponse {
  code?: string;
  message?: string;
  detail?: string | ValidationError[];
}

const errorMessagesByType: Record<string, string> = {
  missing: "Campo obligatorio",
  string_too_short: "Campo obligatorio",
  too_short: "Debe contener al menos 1 elemento",
  string_type: "Debe ser texto",
  int_type: "Debe ser un número",
  int_parsing: "Debe ser un número entero válido",
};

function getErrorMessage(type: string, msg: string): string {
  return errorMessagesByType[type] || msg;
}

function parseFieldErrors(detail: unknown): Record<string, string> {
  const fieldErrors: Record<string, string> = {};

  if (!Array.isArray(detail)) {
    return fieldErrors;
  }

  for (const error of detail) {
    if (
      typeof error === "object" &&
      error !== null &&
      "loc" in error &&
      "type" in error &&
      "msg" in error
    ) {
      const validationError = error as ValidationError;
      const loc = validationError.loc;

      if (Array.isArray(loc) && loc.length > 1) {
        // Remove "body" prefix and join with dots
        const fieldPath = loc.slice(1).join(".");
        const message = getErrorMessage(validationError.type, validationError.msg);
        fieldErrors[fieldPath] = message;
      }
    }
  }

  return fieldErrors;
}

export class ApiError extends Error {
  readonly fieldErrors: Record<string, string>;

  constructor(
    readonly kind: ApiErrorKind,
    readonly status: number,
    message: string,
    readonly code?: string,
    readonly errorResponse?: ApiErrorResponse,
  ) {
    super(message);
    this.name = "ApiError";

    // Parse field errors from validation response
    if (
      Array.isArray(errorResponse?.detail) &&
      errorResponse.detail.length > 0
    ) {
      this.fieldErrors = parseFieldErrors(errorResponse.detail);
    } else {
      this.fieldErrors = {};
    }
  }
}

export interface ApiClient {
  get<TResponse>(path: string): Promise<TResponse>;
  post<TResponse>(path: string, body: unknown): Promise<TResponse>;
  delete<TResponse>(path: string): Promise<TResponse>;
}

function kindForStatus(status: number): ApiErrorKind {
  if (status === 401) return "unauthenticated";
  if (status === 403) return "forbidden";
  return "failed";
}

/** The only place that calls fetch and attaches the token. Components never call fetch. */
export function createApiClient({ baseUrl }: { baseUrl: string }): ApiClient {
  if (!baseUrl || !baseUrl.trim()) {
    throw new Error("baseUrl must not be empty");
  }

  async function request<TResponse>(path: string, init: RequestInit): Promise<TResponse> {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");

    // Get token from oidc-client-ts UserManager
    const user = await getUserManager().getUser();
    if (user && !user.expired && user.id_token) {
      headers.set("Authorization", `Bearer ${user.id_token}`);
    }

    const response = await fetch(`${baseUrl}${path}`, { ...init, headers });

    if (!response.ok) {
      // Parse error response to include code and message
      let errorResponse: ApiErrorResponse = {};
      try {
        errorResponse = (await response.json()) as ApiErrorResponse;
      } catch {
        // If response is not JSON, that's OK
      }

      const kind = kindForStatus(response.status);

      // Build message: always string, never [object Object]
      let message: string;
      if (errorResponse.message) {
        message = errorResponse.message;
      } else if (typeof errorResponse.detail === "string") {
        message = errorResponse.detail;
      } else if (Array.isArray(errorResponse.detail)) {
        // Validation errors: use generic message, details are in fieldErrors
        message = "Hay campos con errores";
      } else {
        message = `Request to ${path} failed`;
      }

      const error = new ApiError(kind, response.status, message, errorResponse.code, errorResponse);

      // On 401, remove the user session
      if (response.status === 401) {
        await getUserManager().removeUser();
      }

      throw error;
    }

    return (await response.json()) as TResponse;
  }

  return {
    get: <TResponse,>(path: string) => request<TResponse>(path, { method: "GET" }),
    delete: <TResponse,>(path: string) => request<TResponse>(path, { method: "DELETE" }),
    post: <TResponse,>(path: string, body: unknown) =>
      request<TResponse>(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
  };
}
