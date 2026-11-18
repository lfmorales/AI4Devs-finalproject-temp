import { PHASE_DEVELOPMENT_SERVER, PHASE_PRODUCTION_BUILD } from "next/constants";
import { afterEach, describe, expect, it, vi } from "vitest";

import nextConfig from "@/next.config";

afterEach(() => vi.unstubAllEnvs());

describe("the production build", () => {
  it("fails, naming both variables, when the Entra tenant and client are empty", () => {
    vi.stubEnv("NEXT_PUBLIC_ENTRA_TENANT_ID", "");
    vi.stubEnv("NEXT_PUBLIC_ENTRA_CLIENT_ID", " ");

    expect(() => nextConfig(PHASE_PRODUCTION_BUILD)).toThrowError(/NEXT_PUBLIC_ENTRA_TENANT_ID.*NEXT_PUBLIC_ENTRA_CLIENT_ID/);
  });

  it("builds the standalone server when both are set", () => {
    vi.stubEnv("NEXT_PUBLIC_ENTRA_TENANT_ID", "tenant-de-prueba");
    vi.stubEnv("NEXT_PUBLIC_ENTRA_CLIENT_ID", "cliente-de-prueba");

    expect(nextConfig(PHASE_PRODUCTION_BUILD).output).toBe("standalone");
  });

  it("is not checked outside the production build: the runtime image does not carry the variables", () => {
    vi.stubEnv("NEXT_PUBLIC_ENTRA_TENANT_ID", "");
    vi.stubEnv("NEXT_PUBLIC_ENTRA_CLIENT_ID", "");

    expect(nextConfig(PHASE_DEVELOPMENT_SERVER).output).toBe("standalone");
  });
});
