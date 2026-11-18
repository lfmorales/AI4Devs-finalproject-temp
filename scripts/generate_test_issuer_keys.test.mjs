// Where the test issuer keys may and may not go: ignored by git, never in a build context sent to Docker,
// mounted (the public half only, read-only) in development and nowhere in production.
// Run from the repository root: node --test scripts/generate_test_issuer_keys.test.mjs
// Needs git and Docker. It builds nothing that stays: each context is exported to a temporary directory.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { cpSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative } from "node:path";
import { after, describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const GENERATE = join(ROOT, "scripts", "generate_test_issuer_keys.sh");
const CONTEXTS = ["backend", "frontend"];
const workDir = mkdtempSync(join(tmpdir(), "test-issuer-keys-test-"));
after(() => rmSync(workDir, { recursive: true, force: true }));

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { cwd: ROOT, encoding: "utf8", timeout: 300_000, ...options });
  return { status: result.status, stdout: result.stdout ?? "", stderr: result.stderr ?? "" };
}

function filesUnder(dir) {
  return readdirSync(dir, { recursive: true })
    .map((name) => join(dir, String(name)))
    .filter((path) => statSync(path).isFile());
}

/** Exports exactly the build context Docker receives for `contextDir`, after its .dockerignore. */
function exportedContext(contextDir) {
  const out = mkdtempSync(join(workDir, "context-"));
  const result = run("docker", ["build", "--quiet", "--output", `type=local,dest=${out}`, "-f", "-", contextDir], {
    input: "FROM scratch\nCOPY . /\n",
  });
  assert.equal(result.status, 0, result.stderr);
  return filesUnder(out).map((path) => relative(out, path));
}

/** A key pair under .secrets/test-issuer inside `dir`, as the script lays it out. */
function generatePairInside(dir) {
  const result = run("bash", [GENERATE, "--out", join(dir, ".secrets", "test-issuer")]);
  assert.equal(result.status, 0, result.stderr);
}

function composeConfig(file) {
  const envFile = join(workDir, "compose.env");
  writeFileSync(envFile, "POSTGRES_USER=u\nPOSTGRES_PASSWORD=p\nPOSTGRES_DB=d\n");
  const result = run(
    "docker",
    ["compose", "-f", file, "--env-file", envFile, "config", "--no-env-resolution", "--format", "json"],
    { env: { ...process.env, ENV_FILE: envFile } },
  );
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

const bindSources = (config) =>
  Object.values(config.services).flatMap((service) => (service.volumes ?? []).map((volume) => volume.source ?? ""));

describe("git ignores the test issuer keys", () => {
  it("reports both keys, and anything else under .secrets/, as ignored", () => {
    const paths = [
      ".secrets/test-issuer/public/public.pem",
      ".secrets/test-issuer/private/private.pem",
      ".secrets/test-issuer/private/notes.txt",
    ];

    const result = run("git", ["check-ignore", ...paths]);

    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(result.stdout.trim().split("\n"), paths);
  });
});

describe("no key reaches a build context sent to Docker", () => {
  for (const context of CONTEXTS) {
    it(`a pair placed inside ${context}/ is left out by its .dockerignore, and nothing else is`, () => {
      const copy = mkdtempSync(join(workDir, `${context}-`));
      cpSync(join(ROOT, context, ".dockerignore"), join(copy, ".dockerignore"));
      mkdirSync(join(copy, "app"));
      writeFileSync(join(copy, "app", "kept.txt"), "control file\n");
      generatePairInside(copy);

      const files = exportedContext(copy);

      assert.deepEqual(files.filter((file) => file !== ".dockerignore"), [join("app", "kept.txt")]);
    });

    it(`the real ${context}/ context holds no .secrets path, no .pem file and no private key`, () => {
      const files = exportedContext(join(ROOT, context));

      assert.deepEqual(files.filter((file) => file.includes(".secrets") || file.endsWith(".pem")), []);
      const withPrivateKey = files.filter((file) =>
        readFileSync(join(ROOT, context, file), "latin1").includes("PRIVATE KEY"),
      );
      assert.deepEqual(withPrivateKey, []);
    });
  }
});

describe("the compose files", () => {
  it("development mounts only the public directory, read-only, and selects the test issuer", () => {
    const config = composeConfig("docker-compose.yml");
    const backend = config.services.backend;

    assert.equal(backend.environment.APP_ENV, "development");
    assert.equal(backend.environment.TEST_ISSUER_PUBLIC_KEY_FILE, "/run/test-issuer/public.pem");
    const keyMounts = (backend.volumes ?? []).filter((volume) => (volume.source ?? "").includes(".secrets"));
    assert.equal(keyMounts.length, 1);
    assert.equal(keyMounts[0].source, join(ROOT, ".secrets", "test-issuer", "public"));
    assert.equal(keyMounts[0].target, "/run/test-issuer");
    assert.equal(keyMounts[0].read_only, true);
    assert.deepEqual(bindSources(config).filter((source) => source.includes("private")), []);
  });

  it("production pins APP_ENV=production and has no key mount and no key variable", () => {
    const config = composeConfig("docker-compose.prod.yml");
    const backend = config.services.backend;

    assert.equal(backend.environment.APP_ENV, "production");
    assert.equal("TEST_ISSUER_PUBLIC_KEY_FILE" in backend.environment, false);
    assert.deepEqual(bindSources(config).filter((source) => source.includes(".secrets")), []);
  });
});
