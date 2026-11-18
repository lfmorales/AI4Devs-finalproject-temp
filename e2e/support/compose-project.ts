import { execFileSync } from "node:child_process";
import { realpathSync } from "node:fs";

export interface Publisher {
  name: string;
  /** The com.docker.compose.project label; empty for a container that is not part of a Compose project. */
  project: string;
  /** The com.docker.compose.project.working_dir label: the folder the stack was started from; empty when absent. */
  workingDir: string;
}

export type ComposeProjectCheck =
  | { status: "ok" }
  | { status: "unavailable"; message: string }
  | { status: "mismatch"; message: string };

const PS_FORMAT = '{{.Names}}|{{.Label "com.docker.compose.project"}}|{{.Label "com.docker.compose.project.working_dir"}}|{{.Ports}}';
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
    .filter(([, , , ports]) => PUBLISHES_HOST_PORT_80.test(ports ?? ""))
    .map(([name = "", project = "", workingDir = ""]) => ({ name, project, workingDir }));
}

/** The folder with symbolic links resolved, so two spellings of the same folder compare equal. */
function canonical(folder: string): string {
  try {
    return realpathSync(folder);
  } catch {
    return folder;
  }
}

/** Why a container is not this repository's stack, or null when it is. */
function foreignReason(publisher: Publisher, project: string, repositoryRoot: string): string | null {
  if (publisher.project === "") return "not a Compose project";
  if (publisher.project !== project) return `project "${publisher.project}"`;
  if (publisher.workingDir === "") {
    return `project "${publisher.project}" with no working directory label, so the folder it was started from is unknown; recreate it with docker compose up -d`;
  }
  if (canonical(publisher.workingDir) !== repositoryRoot) return `project "${publisher.project}" started from ${publisher.workingDir}`;
  return null;
}

/** The project name Compose resolves for the repository directory, which honours COMPOSE_PROJECT_NAME. */
export function currentComposeProject(options: { searchPath?: string; cwd?: string } = {}): string {
  const config = JSON.parse(docker(["compose", "config", "--format", "json"], options)) as { name?: string };
  if (!config.name) throw new Error("Compose reported no project name.");
  return config.name;
}

/**
 * Whether the containers that publish port 80 belong to this directory's Compose project and were started from this
 * directory: two folders can share a project name, and then only the folder tells their stacks apart. It only reads,
 * and when docker cannot answer it says so instead of failing: the other checks of the setup still apply.
 */
export function checkComposeProject(searchPath?: string, cwd?: string): ComposeProjectCheck {
  const repositoryRoot = canonical(cwd ?? process.cwd());
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
  const foreign = publishers
    .map((publisher) => ({ publisher, reason: foreignReason(publisher, project, repositoryRoot) }))
    .filter(({ reason }) => reason !== null);
  if (foreign.length === 0) return { status: "ok" };

  const described = foreign.map(({ publisher, reason }) => `${publisher.name} (${reason})`).join(", ");
  return {
    status: "mismatch",
    message: `Port 80 is published by ${described}, not by this repository's Compose project "${project}" started from ${repositoryRoot}. Stop that stack or run the E2E from its own worktree.`,
  };
}
