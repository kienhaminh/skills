import {
  existsSync,
  lstatSync,
  mkdirSync,
  readlinkSync,
  readdirSync,
  rmSync,
  symlinkSync,
} from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourceRoot = resolve(repositoryRoot, "skills");
const agentDirectories = {
  codex: ".codex/skills",
  claude: ".claude/skills",
  agents: ".agents/skills",
};

function usage(exitCode = 0) {
  console.log(`Usage: npm run link:project -- --project <path> [options]

Options:
  --agent <codex|claude|agents>  Target skill harness (default: codex)
  --skill <slug[,slug]>          Link one or more skills (default: all skills)
  --unlink                       Remove only links owned by this library
  --check                        Verify that requested skills are linked
  --help                         Show this help
`);
  process.exit(exitCode);
}

function readArguments(argumentsList) {
  const options = { agent: "codex", skills: [], mode: "link" };

  for (let index = 0; index < argumentsList.length; index += 1) {
    const argument = argumentsList[index];
    if (argument === "--help") usage();
    if (argument === "--unlink") {
      options.mode = "unlink";
      continue;
    }
    if (argument === "--check") {
      options.mode = "check";
      continue;
    }
    if (["--project", "--agent", "--skill"].includes(argument)) {
      const value = argumentsList[index + 1];
      if (!value || value.startsWith("--")) {
        console.error(`Missing value for ${argument}.`);
        usage(1);
      }
      index += 1;
      if (argument === "--project") options.project = value;
      if (argument === "--agent") options.agent = value;
      if (argument === "--skill") options.skills.push(...value.split(",").filter(Boolean));
      continue;
    }
    console.error(`Unknown argument: ${argument}`);
    usage(1);
  }

  if (!options.project) {
    console.error("--project is required.");
    usage(1);
  }
  if (!agentDirectories[options.agent]) {
    console.error(`Unsupported agent: ${options.agent}.`);
    usage(1);
  }
  return options;
}

function availableSkills() {
  return readdirSync(sourceRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && existsSync(resolve(sourceRoot, entry.name, "SKILL.md")))
    .map((entry) => entry.name)
    .sort();
}

function isOwnedLink(target, source) {
  if (!existsSync(target) || !lstatSync(target).isSymbolicLink()) return false;
  return resolve(dirname(target), readlinkSync(target)) === source;
}

const options = readArguments(process.argv.slice(2));
const projectRoot = resolve(options.project);
const projectGitEntry = resolve(projectRoot, ".git");
if (!existsSync(projectRoot) || !existsSync(projectGitEntry)) {
  console.error(`${projectRoot} is not a Git checkout. Pass the project root, not a subdirectory.`);
  process.exit(1);
}

const requestedSkills = options.skills.length ? [...new Set(options.skills)] : availableSkills();
const unknownSkills = requestedSkills.filter((skill) => !availableSkills().includes(skill));
if (unknownSkills.length) {
  console.error(`Unknown skill(s): ${unknownSkills.join(", ")}.`);
  process.exit(1);
}

const targetRoot = resolve(projectRoot, agentDirectories[options.agent]);
let failures = 0;

for (const skill of requestedSkills) {
  const source = resolve(sourceRoot, skill);
  const target = resolve(targetRoot, skill);
  const owned = isOwnedLink(target, source);

  if (options.mode === "check") {
    console.log(`${owned ? "OK" : "MISSING"} ${options.agent} ${skill}`);
    failures += owned ? 0 : 1;
    continue;
  }

  if (options.mode === "unlink") {
    if (owned) {
      rmSync(target);
      console.log(`Unlinked ${options.agent} ${skill}`);
    } else if (existsSync(target)) {
      console.error(`Refusing to remove ${target}: it is not this library's link.`);
      failures += 1;
    } else {
      console.log(`Not linked ${options.agent} ${skill}`);
    }
    continue;
  }

  mkdirSync(targetRoot, { recursive: true });
  if (owned) {
    console.log(`Already linked ${options.agent} ${skill}`);
  } else if (existsSync(target)) {
    console.error(`Refusing to replace existing ${target}. Remove or rename it yourself first.`);
    failures += 1;
  } else {
    symlinkSync(source, target, "dir");
    console.log(`Linked ${options.agent} ${skill} -> ${source}`);
  }
}

process.exit(failures ? 1 : 0);
