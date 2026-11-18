// Tests of the test-issuer token, the Entra session object and the seeding SQL of the E2E users.
// Run from e2e/: node --test support/test-issuer.test.mjs. Nothing here touches the stack or the repository's keys.
import assert from "node:assert/strict";
import { generateKeyPairSync, verify } from "node:crypto";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, describe, it } from "node:test";

import { buildSeedSql, E2E_USERS } from "./e2e-users.ts";
import { isMicrosoftSignIn, readEntraSettings, readSessions, sessionStorageEntry, writeSessions } from "./session.ts";
import { readPrivateKey, signTestIssuerToken, TEST_AUDIENCE, TEST_ISSUER } from "./test-issuer.ts";

const workDir = mkdtempSync(join(tmpdir(), "test-issuer-test-"));
after(() => rmSync(workDir, { recursive: true, force: true }));

const { privateKey, publicKey } = generateKeyPairSync("rsa", {
  modulusLength: 2048,
  privateKeyEncoding: { type: "pkcs8", format: "pem" },
  publicKeyEncoding: { type: "spki", format: "pem" },
});
const NOW = 1_800_000_000;
const OPERATIONS = E2E_USERS.find((user) => user.name === "operations");

const decode = (segment) => JSON.parse(Buffer.from(segment, "base64url").toString("utf8"));

describe("the test-issuer token", () => {
  it("is an RS256 JWT that the matching public key verifies", () => {
    const token = signTestIssuerToken(OPERATIONS, privateKey, NOW);
    const [header, payload, signature] = token.split(".");

    assert.deepEqual(decode(header), { alg: "RS256", typ: "JWT" });
    assert.equal(verify("sha256", Buffer.from(`${header}.${payload}`), publicKey, Buffer.from(signature, "base64url")), true);
  });

  it("carries exactly the claims of an Entra access token of the test issuer, valid for four hours", () => {
    const claims = decode(signTestIssuerToken(OPERATIONS, privateKey, NOW).split(".")[1]);

    assert.deepEqual(claims, {
      iss: "http://localhost/test-issuer/v2.0",
      aud: "api://adops360-test-issuer",
      iat: NOW,
      exp: NOW + 4 * 3600,
      ver: "2.0",
      scp: "access_as_user",
      oid: "e2e-operations",
      tid: "e2e-test-tenant",
      email: "e2e-operations@adops360.example.test",
    });
    assert.deepEqual([TEST_ISSUER, TEST_AUDIENCE], [claims.iss, claims.aud]);
  });

  it("fails without the private key, naming the script that generates it", () => {
    assert.throws(() => readPrivateKey(join(workDir, "missing.pem")), /Run scripts\/generate_test_issuer_keys\.sh/);
  });

  it("reads an existing private key", () => {
    const path = join(workDir, "private.pem");
    writeFileSync(path, privateKey);

    assert.equal(readPrivateKey(path), privateKey);
  });
});

describe("the Entra session object", () => {
  const settings = { tenantId: "tenant-de-prueba", clientId: "cliente-de-prueba" };

  it("is stored under the key oidc-client-ts builds from the frontend's Entra authority and client", () => {
    const { key } = sessionStorageEntry(settings, signTestIssuerToken(OPERATIONS, privateKey, NOW));

    assert.equal(key, "oidc.user:https://login.microsoftonline.com/tenant-de-prueba/v2.0:cliente-de-prueba");
  });

  it("holds the token as the access token, the email in the profile and the token's expiry", () => {
    const token = signTestIssuerToken(OPERATIONS, privateKey, NOW);

    const stored = JSON.parse(sessionStorageEntry(settings, token).value);

    assert.equal(stored.access_token, token);
    assert.equal(stored.token_type, "Bearer");
    assert.equal(stored.scope, "openid profile email api://cliente-de-prueba/access_as_user");
    assert.equal(stored.profile.email, "e2e-operations@adops360.example.test");
    assert.equal(stored.profile.sub, "e2e-operations");
    assert.equal(stored.expires_at, NOW + 4 * 3600);
    assert.equal("id_token" in stored, false);
  });

  it("reads ENTRA_TENANT_ID and ENTRA_CLIENT_ID by name: the last assignment, unquoted and trimmed", () => {
    const env = 'ENTRA_TENANT_ID=old\nOTHER=1\nENTRA_TENANT_ID= "tenant-de-prueba" \r\nENTRA_CLIENT_ID=\'cliente-de-prueba\'\n';

    assert.deepEqual(readEntraSettings(env), settings);
  });

  it("names the missing variables without echoing any value", () => {
    assert.throws(
      () => readEntraSettings("ENTRA_TENANT_ID=valor-secreto\nENTRA_CLIENT_ID=\n"),
      (error) => /ENTRA_CLIENT_ID/.test(error.message) && !error.message.includes("valor-secreto"),
    );
  });
});

describe("the E2E users and their seeding", () => {
  it("are one user per role plus the two unions of the access matrix, each with a fixed oid", () => {
    assert.deepEqual(
      E2E_USERS.map((user) => [user.name, user.email, user.oid, user.roles]),
      [
        ["operations", "e2e-operations@adops360.example.test", "e2e-operations", ["operations"]],
        ["business", "e2e-business@adops360.example.test", "e2e-business", ["business"]],
        ["finance", "e2e-finance@adops360.example.test", "e2e-finance", ["finance"]],
        ["trading", "e2e-trading@adops360.example.test", "e2e-trading", ["trading"]],
        ["finance-trading", "e2e-finance-trading@adops360.example.test", "e2e-finance-trading", ["finance", "trading"]],
        ["business-trading", "e2e-business-trading@adops360.example.test", "e2e-business-trading", ["business", "trading"]],
      ],
    );
  });

  it("is one transaction that names no address outside the fixed list", () => {
    const sql = buildSeedSql(E2E_USERS);

    assert.match(sql, /^BEGIN;\n/);
    assert.match(sql, /\nCOMMIT;\n$/);
    const addresses = new Set(sql.match(/[\w.-]+@[\w.-]+/g));
    assert.deepEqual([...addresses].sort(), E2E_USERS.map((user) => user.email).sort());
  });

  it("reactivates the users, clears their link so the first access links them by email again, and sets exactly their roles", () => {
    const sql = buildSeedSql(E2E_USERS);

    assert.match(sql, /ON CONFLICT \(email\) DO UPDATE SET is_active = true, identity_issuer = NULL, identity_subject = NULL/);
    assert.match(sql, /DELETE FROM user_roles WHERE user_id IN \(SELECT id FROM users WHERE email IN \(/);
    assert.match(sql, /RAISE EXCEPTION/);
  });

  it("refuses an address outside @adops360.example.test and an unknown role", () => {
    assert.throws(() => buildSeedSql([{ ...OPERATIONS, email: "someone@example.com" }]), /adops360\.example\.test/);
    assert.throws(() => buildSeedSql([{ ...OPERATIONS, roles: ["admin"] }]), /Unknown role/);
  });
});

describe("the Microsoft sign-in hosts the E2E block", () => {
  it("are login.microsoftonline.com and login.microsoft.com, over any path", () => {
    assert.equal(isMicrosoftSignIn("https://login.microsoftonline.com/tenant/v2.0/.well-known/openid-configuration"), true);
    assert.equal(isMicrosoftSignIn("https://login.microsoft.com/common/oauth2/v2.0/authorize"), true);
  });

  it("leave the stack and every other host alone", () => {
    assert.equal(isMicrosoftSignIn("http://localhost/api/users/me"), false);
    assert.equal(isMicrosoftSignIn("https://graph.microsoft.com/v1.0/me"), false);
    assert.equal(isMicrosoftSignIn("https://login.microsoftonline.com.example.test/"), false);
  });
});

describe("the sessions the global setup leaves for the specs", () => {
  it("are read back as written, by user name", () => {
    const path = join(workDir, "auth", "sessions.json");
    const sessions = { operations: { token: "t", key: "k", value: "v" } };

    writeSessions(path, sessions);

    assert.deepEqual(readSessions(path), sessions);
  });

  it("are missing until the global setup has run, and the error says so", () => {
    assert.throws(() => readSessions(join(workDir, "none.json")), /global setup/);
  });
});
