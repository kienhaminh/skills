#!/usr/bin/env python3
"""Inspect stack, agent affordances, and local Markdown links without dependencies."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


IGNORED = {
    ".claude", ".codex", ".git", ".next", ".turbo", ".venv",
    "build", "dist", "node_modules", "target", "vendor",
}
MANIFESTS = {
    "package.json": "javascript-typescript",
    "pyproject.toml": "python",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "Package.swift": "swift",
    "Gemfile": "ruby",
    "pom.xml": "java",
    "build.gradle": "java-kotlin",
    "build.gradle.kts": "java-kotlin",
}
LOCKS = {
    "pnpm-lock.yaml", "yarn.lock", "package-lock.json", "bun.lock", "bun.lockb",
    "uv.lock", "poetry.lock", "Pipfile.lock", "Cargo.lock", "go.sum", "Package.resolved",
    "Gemfile.lock", "gradle.lockfile",
}
VERSION_FILES = {".nvmrc", ".node-version", ".python-version", ".ruby-version", ".swift-version", "rust-toolchain.toml"}
INSTRUCTION_NAMES = {"AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md"}
COMMAND_SURFACE_NAMES = {
    "Makefile", "makefile", "Justfile", "justfile", "Taskfile.yml", "Taskfile.yaml",
    "tox.ini", "noxfile.py", "Pipfile", "Rakefile", "mvnw", "gradlew",
}
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
LEGACY_NAME = re.compile(r"(^|[._-])(legacy|deprecated|obsolete|backup|bak|old|archive)([._-]|$)", re.IGNORECASE)
TRANSIENT_SUFFIXES = {".bak", ".orig", ".rej", ".tmp"}


def walk(root: Path):
    for directory, names, files in os.walk(root):
        names[:] = sorted(name for name in names if name not in IGNORED)
        base = Path(directory)
        for name in names:
            yield base / name
        for name in sorted(files):
            yield base / name


def rels(root: Path, predicate) -> list[str]:
    return sorted(str(path.relative_to(root)) for path in walk(root) if predicate(path))


def package_scripts(root: Path) -> dict[str, str]:
    declared: dict[str, str] = {}
    packages = (path for path in walk(root) if path.is_file() and path.name == "package.json")
    for package in packages:
        try:
            value = json.loads(package.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        scripts = value.get("scripts", {})
        if not isinstance(scripts, dict):
            continue
        relative = str(package.relative_to(root))
        for name, command in sorted(scripts.items()):
            if isinstance(command, str):
                declared[f"{relative}#{name}"] = command
    return declared


def broken_links(root: Path) -> list[dict[str, str]]:
    broken: list[dict[str, str]] = []
    for doc in (path for path in walk(root) if path.is_file() and path.suffix.lower() == ".md"):
        try:
            text = doc.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in MARKDOWN_LINK.finditer(text):
            raw = match.group(1).strip().split()[0].strip("<>")
            if not raw or raw.startswith(("#", "http://", "https://", "mailto:", "data:")):
                continue
            target = raw.split("#", 1)[0]
            if target and not (doc.parent / target).resolve().exists():
                broken.append({"document": str(doc.relative_to(root)), "target": raw})
    return broken


def cleanup_signals(root: Path, lockfiles: list[str]) -> dict[str, list[str]]:
    paths = list(walk(root))
    lockfile_families = sorted({Path(path).name for path in lockfiles})
    return {
        "legacy_named_paths": sorted(
            str(path.relative_to(root)) for path in paths if LEGACY_NAME.search(path.name)
        ),
        "transient_artifacts": sorted(
            str(path.relative_to(root))
            for path in paths
            if path.is_file() and path.suffix.lower() in TRANSIENT_SUFFIXES
        ),
        "multiple_lockfile_families": lockfile_families if len(lockfile_families) > 1 else [],
    }


def inspect(root: Path) -> dict[str, Any]:
    manifests = rels(root, lambda path: path.is_file() and path.name in MANIFESTS)
    stacks = sorted({MANIFESTS[Path(path).name] for path in manifests})
    lockfiles = rels(root, lambda path: path.is_file() and path.name in LOCKS)
    scripts = package_scripts(root)
    return {
        "root": str(root),
        "stacks": stacks,
        "manifests": manifests,
        "lockfiles": lockfiles,
        "version_pins": rels(root, lambda path: path.is_file() and path.name in VERSION_FILES),
        "declared_package_scripts": scripts,
        "command_surfaces": rels(
            root,
            lambda path: path.is_file()
            and (path.name in COMMAND_SURFACE_NAMES or path.name in MANIFESTS),
        ),
        "env_examples": rels(root, lambda path: path.is_file() and (path.name.endswith(".env.example") or path.name == ".env.sample")),
        "containers": rels(root, lambda path: path.is_file() and (path.name.startswith("docker-compose") or path.name in {"compose.yml", "compose.yaml", "Dockerfile"})),
        "ci": rels(root, lambda path: path.is_file() and (".github/workflows" in str(path.relative_to(root)) or path.name in {".gitlab-ci.yml", "Jenkinsfile"})),
        "tests": rels(root, lambda path: path.is_file() and ("test" in path.name.lower() or "spec" in path.name.lower())),
        "instruction_files": rels(
            root, lambda path: path.is_file() and path.name in INSTRUCTION_NAMES
        ),
        "documentation": rels(
            root, lambda path: path.is_file() and path.suffix.lower() == ".md"
        ),
        "cleanup_signals": cleanup_signals(root, lockfiles),
        "broken_markdown_links": broken_links(root),
    }


def markdown(report: dict[str, Any]) -> str:
    lines = ["# Codebase inspection", "", f"Root: `{report['root']}`", ""]
    for key in ("stacks", "manifests", "lockfiles", "version_pins", "env_examples", "containers", "ci"):
        values = report[key]
        rendered = ", ".join(f"`{value}`" for value in values) if values else "none detected"
        lines.extend([f"## {key.replace('_', ' ').title()}", "", rendered, ""])
    lines.extend(["## Declared package scripts", ""])
    lines.extend(
        [f"- `{name}`: `{command}`" for name, command in report["declared_package_scripts"].items()]
        or ["- none detected; inspect the command surfaces below"]
    )
    for heading, key in (
        ("Command surfaces", "command_surfaces"),
        ("Repository instruction files", "instruction_files"),
        ("Documentation files", "documentation"),
    ):
        lines.extend(["", f"## {heading}", ""])
        lines.extend([f"- `{value}`" for value in report[key]] or ["- none detected"])
    lines.extend(["", "## Broken Markdown links", ""])
    lines.extend(
        [f"- `{item['document']}` -> `{item['target']}`" for item in report["broken_markdown_links"]]
        or ["- none detected"]
    )
    lines.extend(["", "## Cleanup signals", "", "Signals require investigation; they are not deletion proof.", ""])
    for name, values in report["cleanup_signals"].items():
        rendered = ", ".join(f"`{value}`" for value in values) if values else "none detected"
        lines.append(f"- {name.replace('_', ' ')}: {rendered}")
    lines.extend(["", f"Detected test-like files: {len(report['tests'])}"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")
    report = inspect(root)
    print(json.dumps(report, indent=2) if args.format == "json" else markdown(report))
    return 1 if report["broken_markdown_links"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
