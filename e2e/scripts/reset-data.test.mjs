// Tests of the port check at the start of reset-data.sh, with a fake docker in the PATH.
// Run: node --test scripts/reset-data.test.mjs. The fake never starts or stops anything.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { after, describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const SCRIPT = join(dirname(fileURLToPath(import.meta.url)), "reset-data.sh");
const workDir = mkdtempSync(join(tmpdir(), "reset-data-test-"));
after(() => rmSync(workDir, { recursive: true, force: true }));

/** Logs every call. `compose down` fails, so a script that gets past the check stops right there. */
function fakeDocker({ ps, project = "mine" }) {
  const dir = mkdtempSync(join(workDir, "bin-"));
  const log = join(dir, "calls.log");
  writeFileSync(join(dir, "docker"), `#!/bin/sh
echo "$@" >> "${log}"
case "$1 $2" in
  "compose config") printf '{"name":"${project}"}' ;;
  "compose down") exit 1 ;;
esac
case "$1" in ps) printf '%s' '${ps}' ;; esac
`);
  chmodSync(join(dir, "docker"), 0o755);
  return { dir, calls: () => { try { return readFileSync(log, "utf8").trim().split("\n"); } catch { return []; } } };
}

const run = (docker) => spawnSync("bash", [SCRIPT], { encoding: "utf8", timeout: 20_000, env: { PATH: `${docker.dir}:${process.env.PATH}`, HOME: process.env.HOME } });
const NGINX = (name, project) => `${name}|${project}|0.0.0.0:80->80/tcp, :::80->80/tcp\n`;

describe("reset-data.sh before it touches anything", () => {
  it("aborts naming the containers and the project when another project publishes port 80, and stops nothing", () => {
    const docker = fakeDocker({ ps: NGINX("other-nginx-1", "other") + NGINX("other-web-1", "other") });

    const result = run(docker);

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /other-nginx-1 \(project "other"\), other-web-1 \(project "other"\)/);
    assert.match(result.stderr, /Compose project "mine"/);
    for (const call of docker.calls()) assert.doesNotMatch(call, /\b(down|up|stop|rm|kill|restart|exec)\b/);
  });

  it("names a container that is not part of any Compose project", () => {
    const docker = fakeDocker({ ps: NGINX("loose-container", "") });

    const result = run(docker);

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /loose-container/);
    assert.match(result.stderr, /not a Compose project/);
  });

  it("goes on to bring this project down when port 80 is this project's own", () => {
    const docker = fakeDocker({ ps: NGINX("mine-nginx-1", "mine") });

    run(docker);

    assert.ok(docker.calls().some((call) => call.startsWith("compose down")));
  });

  it("goes on when nothing publishes port 80", () => {
    const docker = fakeDocker({ ps: "" });

    run(docker);

    assert.ok(docker.calls().some((call) => call.startsWith("compose down")));
  });

  it("aborts when docker is not available", () => {
    const empty = mkdtempSync(join(workDir, "empty-"));

    const result = spawnSync("/bin/bash", [SCRIPT], { encoding: "utf8", timeout: 20_000, env: { PATH: `${empty}:/usr/bin:/bin`, HOME: process.env.HOME } });

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /docker/i);
  });
});
