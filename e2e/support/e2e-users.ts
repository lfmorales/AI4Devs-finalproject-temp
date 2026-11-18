export type RoleName = "operations" | "business" | "finance" | "trading";

/** A user the E2E sign in as: a session of the test issuer, never a person of the Entra tenant. */
export interface E2eUser {
  /** The profile it stands for in the specs. */
  name: string;
  email: string;
  /** The `oid` of its tokens: fixed, so every run presents the same identity. */
  oid: string;
  roles: RoleName[];
}

const ROLE_NAMES: readonly RoleName[] = ["operations", "business", "finance", "trading"];
/** Every E2E address ends here; the seeding refuses any other, so it can never touch a real user. */
export const E2E_EMAIL_DOMAIN = "@adops360.example.test";

const user = (name: string, roles: RoleName[]): E2eUser => ({
  name,
  email: `e2e-${name}${E2E_EMAIL_DOMAIN}`,
  oid: `e2e-${name}`,
  roles,
});

/** One user per role, plus the two unions the access matrix checks. */
export const E2E_USERS: readonly E2eUser[] = [
  user("operations", ["operations"]),
  user("business", ["business"]),
  user("finance", ["finance"]),
  user("trading", ["trading"]),
  user("finance-trading", ["finance", "trading"]),
  user("business-trading", ["business", "trading"]),
];

const literal = (value: string): string => `'${value.replace(/'/g, "''")}'`;

/**
 * One transaction that leaves exactly these users, active, unlinked and with exactly their roles, and touches no
 * other row: every statement is limited to their addresses. Clearing the link makes the first access of every run
 * link them by email again. It fails, and changes nothing, if a role row is missing.
 */
export function buildSeedSql(users: readonly E2eUser[]): string {
  for (const candidate of users) {
    if (!candidate.email.endsWith(E2E_EMAIL_DOMAIN)) throw new Error(`An E2E user must have an address ending in ${E2E_EMAIL_DOMAIN}.`);
    if (candidate.roles.some((role) => !ROLE_NAMES.includes(role))) throw new Error("Unknown role for an E2E user.");
  }
  const emails = users.map((candidate) => literal(candidate.email)).join(", ");
  const expectedRoleRows = users.reduce((count, candidate) => count + candidate.roles.length, 0);
  const upserts = users.map(
    (candidate) =>
      `INSERT INTO users (email, full_name, is_active) VALUES (${literal(candidate.email)}, ${literal(`E2E ${candidate.name}`)}, true) ` +
      `ON CONFLICT (email) DO UPDATE SET is_active = true, identity_issuer = NULL, identity_subject = NULL;\n`,
  );
  const grants = users.map(
    (candidate) =>
      `INSERT INTO user_roles (user_id, role_id) SELECT u.id, r.id FROM users u CROSS JOIN roles r ` +
      `WHERE u.email = ${literal(candidate.email)} AND r.name IN (${candidate.roles.map(literal).join(", ")});\n`,
  );
  return (
    `BEGIN;\n` +
    upserts.join("") +
    `DELETE FROM user_roles WHERE user_id IN (SELECT id FROM users WHERE email IN (${emails}));\n` +
    grants.join("") +
    `DO $$ BEGIN IF (SELECT count(*) FROM user_roles ur JOIN users u ON u.id = ur.user_id WHERE u.email IN (${emails})) <> ${expectedRoleRows} ` +
    `THEN RAISE EXCEPTION 'E2E role rows missing'; END IF; END $$;\n` +
    `COMMIT;\n`
  );
}
