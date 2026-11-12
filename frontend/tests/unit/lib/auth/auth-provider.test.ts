import type { User } from "oidc-client-ts";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  bearerTokenOf,
  buildProviderSettings,
  displayEmailOf,
  readAuthProvider,
} from "@/lib/auth/auth-provider";
import { buildUserManagerSettings } from "@/lib/auth/cognito-config";

afterEach(() => vi.unstubAllEnvs());

function stubCognito() {
  vi.stubEnv("NEXT_PUBLIC_COGNITO_REGION", "eu-central-1");
  vi.stubEnv("NEXT_PUBLIC_COGNITO_USER_POOL_ID", "eu-central-1_Example1");
  vi.stubEnv("NEXT_PUBLIC_COGNITO_CLIENT_ID", "example-client-id");
  vi.stubEnv("NEXT_PUBLIC_COGNITO_DOMAIN", "adops360-example.auth.eu-central-1.amazoncognito.com");
}

function stubEntra() {
  vi.stubEnv("NEXT_PUBLIC_ENTRA_TENANT_ID", "tenant-de-prueba");
  vi.stubEnv("NEXT_PUBLIC_ENTRA_CLIENT_ID", "cliente-de-prueba");
}

const user = (fields: Record<string, unknown>) => fields as unknown as User;

describe("the auth provider setting", () => {
  it("is cognito when the variable is not set", () => {
    vi.stubEnv("NEXT_PUBLIC_AUTH_PROVIDER", undefined);

    expect(readAuthProvider()).toBe("cognito");
  });

  it("is cognito when the variable is blank", () => {
    vi.stubEnv("NEXT_PUBLIC_AUTH_PROVIDER", "  ");

    expect(readAuthProvider()).toBe("cognito");
  });

  it.each(["cognito", "entra"] as const)("accepts %s", (value) => {
    vi.stubEnv("NEXT_PUBLIC_AUTH_PROVIDER", value);

    expect(readAuthProvider()).toBe(value);
  });

  it("refuses any other value with a message that names the variable and the accepted values", () => {
    vi.stubEnv("NEXT_PUBLIC_AUTH_PROVIDER", "azure");

    expect(() => readAuthProvider()).toThrowError(/NEXT_PUBLIC_AUTH_PROVIDER.*"cognito".*"entra"/);
  });

  it("does not accept another capitalisation", () => {
    vi.stubEnv("NEXT_PUBLIC_AUTH_PROVIDER", "Entra");

    expect(() => readAuthProvider()).toThrowError(/NEXT_PUBLIC_AUTH_PROVIDER/);
  });
});

describe("the settings of each provider", () => {
  it("are, for the default provider, exactly the Cognito settings of today", () => {
    stubCognito();
    const cognito = {
      region: "eu-central-1",
      userPoolId: "eu-central-1_Example1",
      clientId: "example-client-id",
      domain: "adops360-example.auth.eu-central-1.amazoncognito.com",
    };

    expect(buildProviderSettings("cognito", "http://localhost")).toEqual(
      buildUserManagerSettings(cognito, "http://localhost"),
    );
  });

  it("derive from the tenant and the client for entra: authority, scope, redirects and flow", () => {
    stubEntra();

    const settings = buildProviderSettings("entra", "http://localhost");

    expect(settings.authority).toBe("https://login.microsoftonline.com/tenant-de-prueba/v2.0");
    expect(settings.client_id).toBe("cliente-de-prueba");
    expect(settings.response_type).toBe("code");
    expect(settings.redirect_uri).toBe("http://localhost/callback");
    expect(settings.post_logout_redirect_uri).toBe("http://localhost");
    expect(settings.scope).toBe("openid profile email api://cliente-de-prueba/access_as_user");
  });

  it("do not ask Entra for offline access or silent renewal", () => {
    stubEntra();

    const settings = buildProviderSettings("entra", "http://localhost");

    expect(settings.scope).not.toContain("offline_access");
    expect(settings.automaticSilentRenew).toBe(false);
  });

  it.each([
    ["tenant", "NEXT_PUBLIC_ENTRA_TENANT_ID"],
    ["client", "NEXT_PUBLIC_ENTRA_CLIENT_ID"],
  ])("fail for entra without the %s, naming the variable", (_name, variable) => {
    stubEntra();
    vi.stubEnv(variable, "");

    expect(() => buildProviderSettings("entra", "http://localhost")).toThrowError(new RegExp(variable));
  });
});

describe("the token that is sent", () => {
  const both = user({ id_token: "token-de-identidad", access_token: "token-de-acceso" });

  it("is the access token for entra", () => {
    expect(bearerTokenOf(both, "entra")).toBe("token-de-acceso");
  });

  it("is the identity token for cognito", () => {
    expect(bearerTokenOf(both, "cognito")).toBe("token-de-identidad");
  });

  it("is null when the token the provider needs is missing, even if the other one is there", () => {
    expect(bearerTokenOf(user({ id_token: "token-de-identidad" }), "entra")).toBeNull();
    expect(bearerTokenOf(user({ access_token: "token-de-acceso" }), "cognito")).toBeNull();
  });
});

describe("the email shown", () => {
  it("is the email claim when there is one", () => {
    expect(displayEmailOf({ email: "a@example.com", preferred_username: "b", name: "c" }, "entra")).toBe("a@example.com");
  });

  it("falls back, for entra, to preferred_username and then to name", () => {
    expect(displayEmailOf({ preferred_username: "b@example.com", name: "c" }, "entra")).toBe("b@example.com");
    expect(displayEmailOf({ name: "Nombre de Prueba" }, "entra")).toBe("Nombre de Prueba");
  });

  it("is empty, never an error, when the profile has nothing to show", () => {
    expect(displayEmailOf({}, "entra")).toBe("");
    expect(displayEmailOf({}, "cognito")).toBe("");
  });

  it("does not fall back for cognito, as today", () => {
    expect(displayEmailOf({ preferred_username: "b@example.com", name: "c" }, "cognito")).toBe("");
  });
});
