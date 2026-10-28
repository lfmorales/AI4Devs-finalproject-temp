// Tests of the Compose project check with a fake docker in the PATH. Run: node --test support/compose-project.test.mjs
import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, describe, it } from "node:test";

import { checkComposeProject } from "./compose-project.ts";

const workDir = mkdtempSync(join(tmpdir(), "compose-project-test-"));
after(() => rmSync(workDir, { recursive: true, force: true }));

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

const line = (name, project, ports) => `${name}|${project}|${ports}\n`;
const NGINX = (name, project) => line(name, project, "0.0.0.0:80->80/tcp, :::80->80/tcp");

describe("the Compose project that publishes port 80", () => {
  it("is fine when it is this project's", () => {
    const docker = fakeDocker({ ps: NGINX("mine-nginx-1", "mine"), project: "mine" });

    assert.equal(checkComposeProject(docker.dir).status, "ok");
  });

  it("is a mismatch when another project publishes it, and names the containers and both projects", () => {
    const docker = fakeDocker({ ps: NGINX("other-nginx-1", "other"), project: "mine" });

    const result = checkComposeProject(docker.dir);

    assert.equal(result.status, "mismatch");
    assert.match(result.message, /other-nginx-1/);
    assert.match(result.message, /"other"/);
    assert.match(result.message, /"mine"/);
  });

  it("honours the project name that Compose reports, not the directory name", () => {
    const docker = fakeDocker({ ps: NGINX("custom-nginx-1", "custom-name"), project: "custom-name" });

    assert.equal(checkComposeProject(docker.dir).status, "ok");
  });

  it("is a mismatch for a container that is not part of any Compose project", () => {
    const docker = fakeDocker({ ps: NGINX("loose-container", ""), project: "mine" });

    const result = checkComposeProject(docker.dir);

    assert.equal(result.status, "mismatch");
    assert.match(result.message, /loose-container/);
    assert.match(result.message, /not a Compose project/);
  });

  it("ignores a container that only maps another host port to its port 80", () => {
    const docker = fakeDocker({ ps: line("other-web-1", "other", "0.0.0.0:8080->80/tcp") + NGINX("mine-nginx-1", "mine"), project: "mine" });

    assert.equal(checkComposeProject(docker.dir).status, "ok");
  });

  it("is a mismatch when no container publishes the port at all", () => {
    const docker = fakeDocker({ ps: "", project: "mine" });

    const result = checkComposeProject(docker.dir);

    assert.equal(result.status, "mismatch");
    assert.match(result.message, /no Docker container publishes port 80/);
  });

  it("warns and goes on when docker cannot be run", () => {
    const docker = fakeDocker({ psFails: true });

    const result = checkComposeProject(docker.dir);

    assert.equal(result.status, "unavailable");
    assert.match(result.message, /docker/i);
  });

  it("warns and goes on when Compose cannot name the project", () => {
    const docker = fakeDocker({ ps: NGINX("mine-nginx-1", "mine"), configFails: true });

    assert.equal(checkComposeProject(docker.dir).status, "unavailable");
  });

  it("warns and goes on when there is no docker in the PATH", () => {
    const empty = mkdtempSync(join(workDir, "empty-"));

    assert.equal(checkComposeProject(empty).status, "unavailable");
  });

  it("only reads: it never stops, removes or starts anything", () => {
    const docker = fakeDocker({ ps: NGINX("other-nginx-1", "other"), project: "mine" });

    checkComposeProject(docker.dir);

    for (const call of docker.calls()) assert.match(call, /^(ps|compose config)\b/);
  });
});
