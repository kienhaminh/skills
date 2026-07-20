#!/usr/bin/env node

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const skillsRoot = join(root, "skills");
const failures = [];
const rows = [];

function fail(skill, message) {
  failures.push(`${skill}: ${message}`);
}

function parseFrontmatter(text, skill) {
  const match = text.match(/^---\n([\s\S]*?)\n---\n/);
  if (!match) {
    fail(skill, "missing YAML frontmatter");
    return {};
  }
  const result = {};
  for (const line of match[1].split("\n")) {
    const separator = line.indexOf(":");
    if (separator === -1) continue;
    result[line.slice(0, separator).trim()] = line.slice(separator + 1).trim();
  }
  return result;
}

function containsNamedFile(directory, name) {
  if (!existsSync(directory)) return false;
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isFile() && entry.name === name) return true;
    if (entry.isDirectory() && containsNamedFile(path, name)) return true;
  }
  return false;
}

const skillNames = readdirSync(skillsRoot)
  .filter((name) => existsSync(join(skillsRoot, name, "SKILL.md")))
  .sort();
const knownSkills = new Set(skillNames);

for (const skill of skillNames) {
  const file = join(skillsRoot, skill, "SKILL.md");
  const text = readFileSync(file, "utf8");
  const frontmatter = parseFrontmatter(text, skill);
  const description = (frontmatter.description ?? "").replace(/^['"]|['"]$/g, "");
  const descriptionWords = description.split(/\s+/).filter(Boolean).length;
  const disabled = frontmatter["disable-model-invocation"] === "true";
  const allowedFields = new Set(["name", "description", "disable-model-invocation"]);

  if (frontmatter.name !== skill) fail(skill, "frontmatter name must match the directory");
  if (!description) fail(skill, "description is required");
  if (descriptionWords > (disabled ? 20 : 45)) {
    fail(skill, `description has ${descriptionWords} words; limit is ${disabled ? 20 : 45}`);
  }
  for (const field of Object.keys(frontmatter)) {
    if (!allowedFields.has(field)) fail(skill, `unsupported frontmatter field ${field}`);
  }
  if (!/\bcomplete(?:d|s|ly)?\b|\bcompletion\b/i.test(text)) {
    fail(skill, "missing an explicit completion criterion");
  }
  if (/\b(?:Vietnam monorepo|AskUserQuestion)\b/i.test(text)) {
    fail(skill, "contains a project- or provider-specific public assumption");
  }

  const metadata = join(skillsRoot, skill, "agents", "openai.yaml");
  if (!existsSync(metadata)) {
    fail(skill, "missing agents/openai.yaml");
  } else {
    const yaml = readFileSync(metadata, "utf8");
    for (const field of ["display_name", "short_description"]) {
      if (!new RegExp(`^\\s*${field}:`, "m").test(yaml)) fail(skill, `metadata missing ${field}`);
    }
    if (!disabled && !/^\s*default_prompt:/m.test(yaml)) fail(skill, "metadata missing default_prompt");
    if (disabled && !/^\s*allow_implicit_invocation:\s*false\s*$/m.test(yaml)) {
      fail(skill, "user-invoked skill metadata must disable implicit invocation");
    }
  }

  for (const match of text.matchAll(/\[[^\]]+\]\(([^)]+)\)/g)) {
    const target = match[1];
    if (/^(?:https?:|#)/.test(target) || /[<>]/.test(target)) continue;
    if (!existsSync(resolve(dirname(file), target))) fail(skill, `missing context-pointer target ${target}`);
  }

  for (const match of text.matchAll(/\$([a-z][a-z0-9-]*)/g)) {
    if (!knownSkills.has(match[1])) fail(skill, `references unavailable skill $${match[1]}`);
  }
  if (!containsNamedFile(join(skillsRoot, skill, "evals"), "results.json")) {
    fail(skill, "missing persisted forward-test results");
  }

  rows.push({ skill, words: text.trim().split(/\s+/).length, descriptionWords, invocation: disabled ? "user" : "model" });
}

for (const row of rows) {
  process.stdout.write(`${row.skill.padEnd(22)} ${row.invocation.padEnd(5)} body=${String(row.words).padStart(4)}w description=${String(row.descriptionWords).padStart(2)}w\n`);
}

if (failures.length) {
  process.stderr.write(`\nSkill audit failed (${failures.length}):\n- ${failures.join("\n- ")}\n`);
  process.exit(1);
}

process.stdout.write(`\nSkill audit passed for ${rows.length} skills.\n`);
