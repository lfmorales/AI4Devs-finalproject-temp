// The Compose project is named adops360 by the compose files, and COMPOSE_PROJECT_NAME or -p still override it.
// Each case runs `docker compose config` in a temporary folder with its own .env (dummy ENTRA_* values), so the
// repository's real .env is never read and the folder's name plays no part. Run: node --test scripts/compose-project-name.test.mjs
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { after, describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const workDir = mkdtempSync(join(tmpdir(), "compose-project-name-test-"));
after(() => rmSync(workDir, { recursive: true, force: true }));

const DUMMY_ENV = "POSTGRES_USER=u\nPOSTGRES_PASSWORD=p\nPOSTGRES_DB=d\nENTRA_TENANT_ID=t\nENTRA_CLIENT_ID=c\n";

/** A folder whose name is not any of the expected project names, with a .env of dummy values plus `extra`. */
function projectFolder(extra = "") {
  const folder = mkdtempSync(join(workDir, "some-checkout-"));
  writeFileSync(join(folder, ".env"), DUMMY_ENV + extra);
  return folder;
}

/** The project name Compose resolves, with no variable of the developer's shell but PATH and HOME. */
function projectName(file, folder, { env = {}, args = [] } = {}) {
  const result = spawnSync(
    "docker",
    ["compose", "-f", join(ROOT, file), "--project-directory", folder, ...args, "config", "--format", "json"],
    { encoding: "utf8", timeout: 30_000, env: { PATH: process.env.PATH, HOME: process.env.HOME, ...env } },
  );
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout).name;
}

for (const file of ["docker-compose.yml", "docker-compose.prod.yml"]) {
  describe(`the project name of ${file}`, () => {
    it("is adops360, whatever the folder is called", () => {
      assert.equal(projectName(file, projectFolder()), "adops360");
    });

    it("is COMPOSE_PROJECT_NAME when the environment sets it", () => {
      assert.equal(projectName(file, projectFolder(), { env: { COMPOSE_PROJECT_NAME: "nombre-del-entorno" } }), "nombre-del-entorno");
    });

    it("is COMPOSE_PROJECT_NAME when the folder's .env sets it", () => {
      assert.equal(projectName(file, projectFolder("COMPOSE_PROJECT_NAME=nombre-del-env\n")), "nombre-del-env");
    });

    it("is the one given with -p, over the .env", () => {
      assert.equal(projectName(file, projectFolder("COMPOSE_PROJECT_NAME=nombre-del-env\n"), { args: ["-p", "nombre-de-p"] }), "nombre-de-p");
    });
  });
}
