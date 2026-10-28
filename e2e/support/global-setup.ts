import { join } from "node:path";

import { BASE_URL } from "../playwright.config";
import { checkComposeProject } from "./compose-project";
import { minutesLeft, readToken } from "./token";

/** Silent renew starts shortly before the token expires and would end the injected session mid-run. */
export const MINIMUM_TOKEN_MINUTES = 10;

async function status(path: string): Promise<number> {
  const response = await fetch(`${BASE_URL}${path}`, { redirect: "manual" });
  await response.body?.cancel();
  return response.status;
}

/**
 * Guards against running the specs on the wrong stack (another project may own port 80) or with a token
 * that is about to expire. Every failure says what to check.
 */
export default async function globalSetup(): Promise<void> {
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
    const compose = checkComposeProject(undefined, join(__dirname, "..", ".."));
    if (compose.status === "mismatch") problems.push(compose.message);
    if (compose.status === "unavailable") console.warn(`Warning: ${compose.message}`);
  } else {
    console.warn(`Warning: ${BASE_URL} is not port 80 of this machine, so its Compose project was not checked.`);
  }

  try {
    const { claims } = readToken();
    const minutes = minutesLeft(claims);
    console.log(`E2E token: ${minutes} minutes left (at least ${MINIMUM_TOKEN_MINUTES} are required).`);
    if (minutes < MINIMUM_TOKEN_MINUTES) {
      problems.push(`The token has ${minutes} minutes left, fewer than ${MINIMUM_TOKEN_MINUTES}. Run e2e/scripts/get-token.sh to get a new one.`);
    }
  } catch (error) {
    problems.push(`${(error as Error).message} Run e2e/scripts/get-token.sh to create it.`);
  }

  if (problems.length > 0) {
    throw new Error(`The E2E environment is not ready:\n - ${problems.join("\n - ")}`);
  }
}
