import { execFileSync } from "node:child_process";

export interface Publisher {
  name: string;
  /** The com.docker.compose.project label; empty for a container that is not part of a Compose project. */
  project: string;
}

export type ComposeProjectCheck =
  | { status: "ok" }
  | { status: "unavailable"; message: string }
  | { status: "mismatch"; message: string };

const PS_FORMAT = '{{.Names}}|{{.Label "com.docker.compose.project"}}|{{.Ports}}';
// A host mapping of the port itself: "0.0.0.0:80->80/tcp" or ":::80->80/tcp", but not "0.0.0.0:8080->80/tcp".
const PUBLISHES_HOST_PORT_80 = /(^|[\s,]):?[^\s,]*:80->/;

function docker(args: string[], options: { searchPath?: string; cwd?: string }): string {
  const env = options.searchPath === undefined ? process.env : { ...process.env, PATH: options.searchPath };
  return execFileSync("docker", args, { encoding: "utf8", env, cwd: options.cwd, stdio: ["ignore", "pipe", "ignore"], timeout: 20_000 });
}

/** The containers that publish host port 80, read-only. */
export function containersPublishingPort80(options: { searchPath?: string } = {}): Publisher[] {
  const output = docker(["ps", "--filter", "publish=80", "--format", PS_FORMAT], options);
  return output
    .split("\n")
    .filter((line) => line.trim() !== "")
    .map((line) => line.split("|"))
    .filter(([, , ports]) => PUBLISHES_HOST_PORT_80.test(ports ?? ""))
    .map(([name = "", project = ""]) => ({ name, project }));
}

/** The project name Compose resolves for the repository directory, which honours COMPOSE_PROJECT_NAME. */
export function currentComposeProject(options: { searchPath?: string; cwd?: string } = {}): string {
  const config = JSON.parse(docker(["compose", "config", "--format", "json"], options)) as { name?: string };
  if (!config.name) throw new Error("Compose reported no project name.");
  return config.name;
}

/**
 * Whether the containers that publish port 80 belong to this directory's Compose project. It only reads, and
 * when docker cannot answer it says so instead of failing: the other checks of the setup still apply.
 */
export function checkComposeProject(searchPath?: string, cwd?: string): ComposeProjectCheck {
  let publishers: Publisher[];
  let project: string;
  try {
    publishers = containersPublishingPort80({ searchPath });
    project = currentComposeProject({ searchPath, cwd });
  } catch {
    return { status: "unavailable", message: "docker (or docker compose) could not be run, so which Compose project answers on port 80 was not checked." };
  }

  if (publishers.length === 0) {
    return { status: "mismatch", message: `The stack answers on port 80 but no Docker container publishes port 80, so it is not this repository's Compose project "${project}".` };
  }
  const foreign = publishers.filter((publisher) => publisher.project !== project);
  if (foreign.length === 0) return { status: "ok" };

  const described = foreign.map((publisher) => `${publisher.name} (${publisher.project === "" ? "not a Compose project" : `project "${publisher.project}"`})`).join(", ");
  return { status: "mismatch", message: `Port 80 is published by ${described}, not by this repository's Compose project "${project}". Stop that stack or run the E2E from its own worktree.` };
}
