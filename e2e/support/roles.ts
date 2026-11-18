import { execFileSync } from "node:child_process";
import { join } from "node:path";

import { buildSeedSql, E2E_USERS } from "./e2e-users";

const REPOSITORY_ROOT = join(__dirname, "..", "..");

/** Runs SQL in the stack's database container. Any failure is reported without the SQL, the output or the command. */
function runSql(sql: string): string {
  try {
    return execFileSync(
      "docker",
      ["compose", "exec", "-T", "db", "sh", "-c", 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -q -A -t -v ON_ERROR_STOP=1'],
      { cwd: REPOSITORY_ROOT, input: sql, encoding: "utf8", stdio: ["pipe", "pipe", "ignore"], timeout: 30_000 },
    );
  } catch {
    throw new Error("The database command failed: is the stack up, and are the four roles migrated (alembic upgrade head)?");
  }
}

/**
 * Leaves the E2E users active, unlinked and with exactly their roles, in one transaction that touches only their
 * @adops360.example.test addresses (see buildSeedSql). Safe to repeat: every run starts from the same state.
 */
export function seedE2eUsers(): void {
  runSql(buildSeedSql(E2E_USERS));
}
