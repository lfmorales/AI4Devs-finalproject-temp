// Tests of the Compose project check with a fake docker in the PATH. Run: node --test support/compose-project.test.mjs
import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, describe, it } from "node:test";

import { checkComposeProject } from "./compose-project.ts";

const workDir = mkdtempSync(join(tmpdir(), "compose-project-test-"));
after(() => rmSync(workDir, { recursive: true, force: true }));
/** The repository root the check compares with, and the folder of a stack started elsewhere. */
const ROOT = mkdtempSync(join(workDir, "repository-"));
const OTHER_FOLDER = mkdtempSync(join(workDir, "other-checkout-"));

/** A docker that logs every call and answers `ps` and `compose config` as given; anything else just succeeds. */
function fakeDocker({ ps = "", project = "mine", psFails = false, configFails = false } = {}) {
  const dir = mkdtempSync(join(workDir, "bin-"));
  const log = join(dir, "calls.log");
  const script = `#!/bin/sh
echo "$@" >> "${log}"
case "$1" in
  ps) ${psFails ? "exit 1" : `printf '%s' '${ps}'`} ;;
  compose) ${configFails ? "exit 1" : `printf '{"name":"${project}"}'`} ;;
esac
`;
  writeFileSync(join(dir, "docker"), script);
  chmodSync(join(dir, "docker"), 0o755);
  return { dir, calls: () => readFileSync(log, "utf8").trim().split("\n") };
}

const line = (name, project, ports, folder = ROOT) => `${name}|${project}|${folder}|${ports}\n`;
const NGINX = (name, project, folder = ROOT) => line(name, project, "0.0.0.0:80->80/tcp, :::80->80/tcp", folder);
const check = (docker) => checkComposeProject(docker.dir, ROOT);

describe("the Compose project that publishes port 80", () => {
  it("is fine when it is this project's", () => {
    const docker = fakeDocker({ ps: NGINX("mine-nginx-1", "mine"), project: "mine" });

    assert.equal(check(docker).status, "ok");
  });

  it("is a mismatch when another project publishes it, and names the containers and both projects", () => {
    const docker = fakeDocker({ ps: NGINX("other-nginx-1", "other"), project: "mine" });

    const result = check(docker);

    assert.equal(result.status, "mismatch");
    assert.match(result.message, /other-nginx-1/);
    assert.match(result.message, /"other"/);
    assert.match(result.message, /"mine"/);
  });

  it("honours the project name that Compose reports, not the directory name", () => {
    const docker = fakeDocker({ ps: NGINX("custom-nginx-1", "custom-name"), project: "custom-name" });

    assert.equal(check(docker).status, "ok");
  });

  it("is a mismatch for a container that is not part of any Compose project", () => {
    const docker = fakeDocker({ ps: NGINX("loose-container", ""), project: "mine" });

    const result = check(docker);

    assert.equal(result.status, "mismatch");
    assert.match(result.message, /loose-container/);
    assert.match(result.message, /not a Compose project/);
  });

  it("is a mismatch when a stack of the same project name was started from another folder, and names that folder", () => {
    const docker = fakeDocker({ ps: NGINX("mine-nginx-1", "mine", OTHER_FOLDER), project: "mine" });

    const result = check(docker);

    assert.equal(result.status, "mismatch");
    assert.match(result.message, /mine-nginx-1/);
    assert.ok(result.message.includes(OTHER_FOLDER), result.message);
  });

  it("is a mismatch, explaining why, when a container carries no working directory label", () => {
    const docker = fakeDocker({ ps: NGINX("mine-nginx-1", "mine", ""), project: "mine" });

    const result = check(docker);

    assert.equal(result.status, "mismatch");
    assert.match(result.message, /mine-nginx-1/);
    assert.match(result.message, /no working directory label/);
  });

  it("ignores a container that only maps another host port to its port 80", () => {
    const docker = fakeDocker({ ps: line("other-web-1", "other", "0.0.0.0:8080->80/tcp") + NGINX("mine-nginx-1", "mine"), project: "mine" });

    assert.equal(check(docker).status, "ok");
  });

  it("is a mismatch when no container publishes the port at all", () => {
    const docker = fakeDocker({ ps: "", project: "mine" });

    const result = check(docker);

    assert.equal(result.status, "mismatch");
    assert.match(result.message, /no Docker container publishes port 80/);
  });

  it("warns and goes on when docker cannot be run", () => {
    const docker = fakeDocker({ psFails: true });

    const result = check(docker);

    assert.equal(result.status, "unavailable");
    assert.match(result.message, /docker/i);
  });

  it("warns and goes on when Compose cannot name the project", () => {
    const docker = fakeDocker({ ps: NGINX("mine-nginx-1", "mine"), configFails: true });

    assert.equal(check(docker).status, "unavailable");
  });

  it("warns and goes on when there is no docker in the PATH", () => {
    const empty = mkdtempSync(join(workDir, "empty-"));

    assert.equal(checkComposeProject(empty, ROOT).status, "unavailable");
  });

  it("only reads: it never stops, removes or starts anything", () => {
    const docker = fakeDocker({ ps: NGINX("other-nginx-1", "other"), project: "mine" });

    check(docker);

    for (const call of docker.calls()) assert.match(call, /^(ps|compose config)\b/);
  });
});
