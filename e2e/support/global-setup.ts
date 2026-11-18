import { readFileSync } from "node:fs";
import { join } from "node:path";

import { chromium } from "@playwright/test";

import { BASE_URL } from "../playwright.config";
import { checkComposeProject } from "./compose-project";
import { E2E_USERS } from "./e2e-users";
import { seedE2eUsers } from "./roles";
import { isMicrosoftSignIn, readEntraSettings, sessionStorageEntry, type StoredSessions, writeSessions } from "./session";
import { readPrivateKey, signTestIssuerToken } from "./test-issuer";

const REPOSITORY_ROOT = join(__dirname, "..", "..");
const PRIVATE_KEY_PATH = join(REPOSITORY_ROOT, ".secrets", "test-issuer", "private", "private.pem");
export const SESSIONS_PATH = join(__dirname, "..", ".auth", "sessions.json");

async function status(path: string): Promise<number> {
  const response = await fetch(`${BASE_URL}${path}`, { redirect: "manual" });
  await response.body?.cancel();
  return response.status;
}

/** The checks that the stack on this port is this branch's. Every problem says what to check. */
async function stackProblems(): Promise<string[]> {
  const problems: string[] = [];

  try {
    const health = await status("/api/health");
    if (health !== 200) problems.push(`${BASE_URL}/api/health answered ${health}, not 200. Is the AdOps360 stack up (docker compose ps)?`);
  } catch {
    problems.push(`Nothing answers at ${BASE_URL}. Start the stack with docker compose up -d.`);
  }

  try {
    const response = await fetch(`${BASE_URL}/api/openapi.json`);
    const schema = (await response.json()) as { paths?: Record<string, unknown> };
    if (!schema.paths || !("/margin" in schema.paths)) {
      problems.push("/api/openapi.json has no /margin path: the stack on this port is not this branch's backend. Rebuild it (docker compose build) or free port 80.");
    }
  } catch {
    problems.push("/api/openapi.json could not be read as JSON: the stack on this port is not the AdOps360 backend.");
  }

  try {
    if ((await status("/margin")) === 404) problems.push(`${BASE_URL}/margin answered 404: the frontend on this port has no margin page. Rebuild the frontend image.`);
  } catch {
    problems.push(`${BASE_URL}/margin could not be reached.`);
  }

  // Port 80 can belong to another worktree's stack that also has /margin; its Compose project gives it away.
  const { hostname, port } = new URL(BASE_URL);
  if ((hostname === "localhost" || hostname === "127.0.0.1") && (port === "" || port === "80")) {
    const compose = checkComposeProject(undefined, REPOSITORY_ROOT);
    if (compose.status === "mismatch") problems.push(compose.message);
    if (compose.status === "unavailable") console.warn(`Warning: ${compose.message}`);
  } else {
    console.warn(`Warning: ${BASE_URL} is not port 80 of this machine, so its Compose project was not checked.`);
  }
  return problems;
}

/** Signs one test-issuer token per E2E user and builds its session entry; nothing of it is printed. */
function signSessions(): StoredSessions {
  const privateKey = readPrivateKey(PRIVATE_KEY_PATH);
  const settings = readEntraSettings(readFileSync(join(REPOSITORY_ROOT, ".env"), "utf8"));
  const sessions: StoredSessions = {};
  for (const user of E2E_USERS) {
    const token = signTestIssuerToken(user, privateKey);
    sessions[user.name] = { token, ...sessionStorageEntry(settings, token) };
  }
  return sessions;
}

/**
 * Links every E2E user and checks it gets its roles. The seeding left them unlinked, so this request is each user's
 * first access, which links it by email to (test issuer, oid). It must stay here, before any spec, and one user at a
 * time: the specs may run in parallel, and two simultaneous first accesses of the same user would both try to link it.
 */
async function linkEachUserInTurn(sessions: StoredSessions): Promise<string[]> {
  const problems: string[] = [];
  for (const user of E2E_USERS) {
    const response = await fetch(`${BASE_URL}/api/users/me`, { headers: { Authorization: `Bearer ${sessions[user.name].token}` } });
    if (response.status !== 200) {
      await response.body?.cancel();
      problems.push(
        `GET /api/users/me answered ${response.status} for the E2E user ${user.name}. Is the test issuer active in the backend ` +
          "(APP_ENV=development and the public key of scripts/generate_test_issuer_keys.sh mounted; docker compose up -d backend)?",
      );
      continue;
    }
    const { roles } = (await response.json()) as { roles: string[] };
    if (JSON.stringify([...roles].sort()) !== JSON.stringify([...user.roles].sort())) {
      problems.push(`The E2E user ${user.name} has the roles [${roles.join(", ")}], not [${user.roles.join(", ")}].`);
    }
  }
  return problems;
}

/**
 * Opens /status with the operations session injected, as every spec does. If the frontend asks to sign in, the session
 * key was not the one the frontend reads: it was built with another Entra authority or client. Any request to a
 * Microsoft sign-in host fails the check too.
 */
async function checkInjectedSessionInBrowser(sessions: StoredSessions): Promise<string[]> {
  const problems: string[] = [];
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext({ baseURL: BASE_URL });
    const microsoftHosts: string[] = [];
    await context.route(isMicrosoftSignIn, (route) => {
      microsoftHosts.push(new URL(route.request().url()).hostname);
      return route.abort();
    });
    const page = await context.newPage();
    const { key, value } = sessions.operations;
    await page.addInitScript((entry) => window.sessionStorage.setItem(entry.key, entry.value), { key, value });
    await page.goto("/status");
    const signIn = page.getByRole("heading", { name: "Por favor, inicia sesión" });
    const navigation = page.getByRole("navigation", { name: "Principal" });
    await signIn.or(navigation).first().waitFor({ timeout: 15_000 });
    if (await signIn.isVisible()) {
      problems.push(
        "The frontend asked to sign in with the injected session: the session key does not match the Entra authority and " +
          "client the frontend was built with. Rebuild the frontend with the ENTRA_* of .env (docker compose build frontend).",
      );
    }
    if (microsoftHosts.length > 0) problems.push(`The frontend sent ${microsoftHosts.length} request(s) to ${[...new Set(microsoftHosts)].join(", ")}.`);
  } finally {
    await browser.close();
  }
  return problems;
}

/**
 * Prepares every run from the same state: checks the stack, seeds the E2E users, signs their sessions, links them one by
 * one and checks that the frontend accepts the injected session. Every failure says what to check.
 */
export default async function globalSetup(): Promise<void> {
  const fail = (problems: string[]): void => {
    if (problems.length > 0) throw new Error(`The E2E environment is not ready:\n - ${problems.join("\n - ")}`);
  };

  fail(await stackProblems());

  let sessions: StoredSessions;
  try {
    seedE2eUsers();
    sessions = signSessions();
  } catch (error) {
    throw new Error(`The E2E environment is not ready:\n - ${(error as Error).message}`);
  }
  writeSessions(SESSIONS_PATH, sessions);

  fail(await linkEachUserInTurn(sessions));
  fail(await checkInjectedSessionInBrowser(sessions));
}
