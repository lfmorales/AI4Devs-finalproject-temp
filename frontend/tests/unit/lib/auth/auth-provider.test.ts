import type { User } from "oidc-client-ts";
import { afterEach, describe, expect, it, vi } from "vitest";

import { bearerTokenOf, buildAuthSettings, displayEmailOf } from "@/lib/auth/auth-provider";

afterEach(() => vi.unstubAllEnvs());

function stubEntra() {
  vi.stubEnv("NEXT_PUBLIC_ENTRA_TENANT_ID", "tenant-de-prueba");
  vi.stubEnv("NEXT_PUBLIC_ENTRA_CLIENT_ID", "cliente-de-prueba");
}

const user = (fields: Record<string, unknown>) => fields as unknown as User;

describe("the Entra settings", () => {
  it("derive from the tenant and the client: authority, scope, redirects and flow", () => {
    stubEntra();

    const settings = buildAuthSettings("http://localhost");

    expect(settings.authority).toBe("https://login.microsoftonline.com/tenant-de-prueba/v2.0");
    expect(settings.client_id).toBe("cliente-de-prueba");
    expect(settings.response_type).toBe("code");
    expect(settings.redirect_uri).toBe("http://localhost/callback");
    expect(settings.post_logout_redirect_uri).toBe("http://localhost");
    expect(settings.scope).toBe("openid profile email api://cliente-de-prueba/access_as_user");
  });

  it("do not ask Entra for offline access or silent renewal", () => {
    stubEntra();

    const settings = buildAuthSettings("http://localhost");

    expect(settings.scope).not.toContain("offline_access");
    expect(settings.automaticSilentRenew).toBe(false);
  });

  it.each([
    ["tenant", "NEXT_PUBLIC_ENTRA_TENANT_ID"],
    ["client", "NEXT_PUBLIC_ENTRA_CLIENT_ID"],
  ])("fail without the %s, naming the variable", (_name, variable) => {
    stubEntra();
    vi.stubEnv(variable, "");

    expect(() => buildAuthSettings("http://localhost")).toThrowError(new RegExp(variable));
  });
});

describe("the token that is sent", () => {
  it("is the access token, even when an identity token is present", () => {
    expect(bearerTokenOf(user({ id_token: "token-de-identidad", access_token: "token-de-acceso" }))).toBe("token-de-acceso");
  });

  it("is null without an access token, even if the identity token is there", () => {
    expect(bearerTokenOf(user({ id_token: "token-de-identidad" }))).toBeNull();
  });
});

describe("the email shown", () => {
  it("is the email claim when there is one", () => {
    expect(displayEmailOf({ email: "a@example.com", preferred_username: "b", name: "c" })).toBe("a@example.com");
  });

  it("falls back to preferred_username and then to name", () => {
    expect(displayEmailOf({ preferred_username: "b@example.com", name: "c" })).toBe("b@example.com");
    expect(displayEmailOf({ name: "Nombre de Prueba" })).toBe("Nombre de Prueba");
  });

  it("is empty, never an error, when the profile has nothing to show", () => {
    expect(displayEmailOf({})).toBe("");
  });
});
