import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

export type RoleName = "operations" | "business" | "finance" | "trading";

const ROLE_NAMES: readonly RoleName[] = ["operations", "business", "finance", "trading"];
const REPOSITORY_ROOT = join(__dirname, "..", "..");
/** Where the roles of the development user are kept while a spec changes them, so an interrupted run can put them back. */
export const BACKUP_PATH = join(__dirname, "..", ".auth", "roles-backup.json");

/**
 * The development user's email, read by name from the repository's .env (the file is never sourced). It is only ever
 * sent to the database through standard input: it appears in no argument, no log and no error message.
 */
function developmentEmail(): string {
  const envPath = join(REPOSITORY_ROOT, ".env");
  if (!existsSync(envPath)) throw new Error("No .env found at the repository root.");
  const assignments = readFileSync(envPath, "utf8").split("\n").filter((line) => line.startsWith("SEED_USER_EMAIL="));
  const raw = assignments.at(-1)?.slice("SEED_USER_EMAIL=".length) ?? "";
  const email = raw.replace(/\r/g, "").trim().replace(/^(["'])(.*)\1$/, "$2").trim();
  if (email === "") throw new Error("SEED_USER_EMAIL is not set in .env.");
  return email;
}

const literal = (value: string): string => `'${value.replace(/'/g, "''")}'`;

/** Runs SQL in the stack's database container. Any failure is reported without the SQL, the output or the command. */
function runSql(sql: string): string {
  try {
    return execFileSync(
      "docker",
      ["compose", "exec", "-T", "db", "sh", "-c", 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -q -A -t -v ON_ERROR_STOP=1'],
      { cwd: REPOSITORY_ROOT, input: sql, encoding: "utf8", stdio: ["pipe", "pipe", "ignore"], timeout: 30_000 },
    );
  } catch {
    throw new Error("The database command failed: is the stack up, and has the trading role been migrated (alembic upgrade head)?");
  }
}

/** The roles the development user holds now. */
export function currentRoles(): RoleName[] {
  const email = literal(developmentEmail());
  const output = runSql(
    `SELECT 'user:' || count(*) FROM users WHERE lower(email) = lower(${email});\n` +
      `SELECT 'role:' || r.name FROM user_roles ur JOIN roles r ON r.id = ur.role_id JOIN users u ON u.id = ur.user_id ` +
      `WHERE lower(u.email) = lower(${email}) ORDER BY r.name;\n`,
  );
  const lines = output.split("\n").map((line) => line.trim()).filter(Boolean);
  if (!lines.includes("user:1")) throw new Error("The development user does not exist in the database.");
  return lines.filter((line) => line.startsWith("role:")).map((line) => line.slice("role:".length) as RoleName);
}

/** Replaces the development user's roles by exactly these, in one transaction that fails if a role row is missing. */
export function setRoles(roles: readonly RoleName[]): void {
  const unknown = roles.filter((role) => !ROLE_NAMES.includes(role));
  if (unknown.length > 0) throw new Error("Unknown role requested.");
  const email = literal(developmentEmail());
  const names = roles.map(literal).join(", ");
  const insert =
    roles.length === 0
      ? ""
      : `INSERT INTO user_roles (user_id, role_id) SELECT u.id, r.id FROM users u CROSS JOIN roles r WHERE lower(u.email) = lower(${email}) AND r.name IN (${names});\n`;
  runSql(
    `BEGIN;\n` +
      `DELETE FROM user_roles WHERE user_id IN (SELECT id FROM users WHERE lower(email) = lower(${email}));\n` +
      insert +
      `DO $$ BEGIN IF (SELECT count(*) FROM user_roles ur JOIN users u ON u.id = ur.user_id WHERE lower(u.email) = lower(${email})) <> ${roles.length} THEN RAISE EXCEPTION 'role rows missing'; END IF; END $$;\n` +
      `COMMIT;\n`,
  );
}

/** Puts back the roles saved before a spec changed them. Returns whether there was anything to put back. */
export function restoreRolesIfBackedUp(): boolean {
  if (!existsSync(BACKUP_PATH)) return false;
  const { roles } = JSON.parse(readFileSync(BACKUP_PATH, "utf8")) as { roles: RoleName[] };
  setRoles(roles);
  rmSync(BACKUP_PATH);
  return true;
}

/**
 * Runs `body` with the development user holding exactly `roles`, and puts the original roles back afterwards, also
 * when `body` fails. The original roles are written to disk first, so a run that is killed can be repaired by the
 * next one (see the global setup).
 */
export async function withRoles<T>(roles: readonly RoleName[], body: () => Promise<T>): Promise<T> {
  if (!existsSync(BACKUP_PATH)) {
    mkdirSync(dirname(BACKUP_PATH), { recursive: true });
    writeFileSync(BACKUP_PATH, JSON.stringify({ roles: currentRoles() }));
  }
  try {
    setRoles(roles);
    return await body();
  } finally {
    restoreRolesIfBackedUp();
  }
}
