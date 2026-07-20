#!/usr/bin/env node

import { cpSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { execFileSync } from "node:child_process";

const [sourceArg, targetArg, branch = "main"] = process.argv.slice(2);
if (!sourceArg || !targetArg) {
  console.error("usage: prepare-eval-repo.mjs <fixture-source> <new-target> [branch]");
  process.exit(64);
}

const source = resolve(sourceArg);
const target = resolve(targetArg);
if (!existsSync(source)) throw new Error(`fixture source does not exist: ${source}`);
if (existsSync(target)) throw new Error(`target already exists: ${target}`);

cpSync(source, target, { recursive: true });
execFileSync("git", ["init", "-q", "-b", branch, target]);
for (const [key, value] of [["user.name", "Skill Eval"], ["user.email", "eval@example.invalid"]]) {
  execFileSync("git", ["-C", target, "config", key, value]);
}
execFileSync("git", ["-C", target, "add", "--all"]);
execFileSync("git", ["-C", target, "commit", "-qm", "chore: seed evaluation fixture"]);
process.stdout.write(`${target}\n`);
