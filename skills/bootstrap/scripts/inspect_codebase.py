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
DOC_OWNERS = {
    "root_runbook": ("README.md",),
    "agent_entrypoint": ("AGENTS.md", "CLAUDE.md"),
    "docs_router": ("docs/README.md",),
    "architecture": ("docs/architecture", "docs/architecture.md"),
    "design": ("docs/design",),
    "conventions": ("docs/CONVENTIONS.md",),
    "security": ("docs/SECURITY.md",),
    "testing": ("docs/TESTING.md",),
    "debugging": ("docs/DEBUG.md",),
    "observation": ("docs/OBSERVATION.md",),
    "planning": ("docs/PLANS.md", "docs/plans"),
    "lessons": ("docs/LESSONS.md",),
}
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
LEGACY_NAME = re.compile(r"(^|[._-])(legacy|deprecated|obsolete|backup|bak|old|archive)([._-]|$)", re.IGNORECASE)
TRANSIENT_SUFFIXES = {".bak", ".orig", ".rej", ".tmp"}
CORE_START = "<!-- bootstrap:core:start -->"
CORE_END = "<!-- bootstrap:core:end -->"
SOURCE_TREE = re.compile(
    r"^## Source tree\s*$.*?^```(?:text)?\s*$\n(?P<body>.*?)^```\s*$",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


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
    package = root / "package.json"
    if not package.is_file():
        return {}
    try:
        value = json.loads(package.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = value.get("scripts", {})
    return scripts if isinstance(scripts, dict) else {}


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


def canonical_agent_core() -> str | None:
    reference = Path(__file__).resolve().parent.parent / "references" / "agent-entrypoints.md"
    try:
        text = reference.read_text(encoding="utf-8")
    except OSError:
        return None
    start = text.find(CORE_START)
    end = text.find(CORE_END, start)
    if start < 0 or end < 0:
        return None
    return text[start:end + len(CORE_END)]


def source_tree_covers_docs(root: Path, body: str | None) -> bool:
    docs = root / "docs"
    if not docs.is_dir():
        return True
    if not body or "docs/" not in body:
        return False
    owners = sorted(path.name for path in docs.iterdir() if path.is_file() and path.suffix.lower() == ".md")
    routers = sorted(f"{path.name}/" for path in docs.iterdir() if path.is_dir() and path.name not in IGNORED)
    return all(name in body for name in owners + routers)


def agent_entrypoints(root: Path) -> dict[str, Any]:
    paths = {name: root / name for name in ("AGENTS.md", "CLAUDE.md")}
    present = {name: path.is_file() for name, path in paths.items()}
    texts: dict[str, str | None] = {}
    for name, path in paths.items():
        try:
            texts[name] = path.read_text(encoding="utf-8") if present[name] else None
        except (OSError, UnicodeDecodeError):
            texts[name] = None
    if not all(present.values()):
        sync = "incomplete"
    elif any(text is None for text in texts.values()):
        sync = "unreadable"
    else:
        sync = "identical" if texts["AGENTS.md"] == texts["CLAUDE.md"] else "different"
    core = canonical_agent_core()
    tree_bodies = {
        name: match.group("body").strip() if text and (match := SOURCE_TREE.search(text)) else None
        for name, text in texts.items()
    }
    return {
        **present,
        "sync": sync,
        "source_tree": {
            name: bool(body) for name, body in tree_bodies.items()
        },
        "docs_coverage": {
            name: source_tree_covers_docs(root, body) for name, body in tree_bodies.items()
        },
        "canonical_core": {
            name: bool(text and core and core in text)
            for name, text in texts.items()
        },
    }


def inspect(root: Path) -> dict[str, Any]:
    manifests = rels(root, lambda path: path.is_file() and path.name in MANIFESTS)
    stacks = sorted({MANIFESTS[Path(path).name] for path in manifests})
    lockfiles = rels(root, lambda path: path.is_file() and path.name in LOCKS)
    scripts = package_scripts(root)
    command_names = ("dev", "build", "type-check", "typecheck", "lint", "format", "test", "test:int", "test:e2e")
    commands = {name: scripts[name] for name in command_names if name in scripts}
    docs = {name: any((root / candidate).exists() for candidate in candidates) for name, candidates in DOC_OWNERS.items()}
    docs["agent_entrypoint"] = all((root / candidate).is_file() for candidate in DOC_OWNERS["agent_entrypoint"])
    return {
        "root": str(root),
        "stacks": stacks,
        "manifests": manifests,
        "lockfiles": lockfiles,
        "version_pins": rels(root, lambda path: path.is_file() and path.name in VERSION_FILES),
        "commands": commands,
        "env_examples": rels(root, lambda path: path.is_file() and (path.name.endswith(".env.example") or path.name == ".env.sample")),
        "containers": rels(root, lambda path: path.is_file() and (path.name.startswith("docker-compose") or path.name in {"compose.yml", "compose.yaml", "Dockerfile"})),
        "ci": rels(root, lambda path: path.is_file() and (".github/workflows" in str(path.relative_to(root)) or path.name in {".gitlab-ci.yml", "Jenkinsfile"})),
        "tests": rels(root, lambda path: path.is_file() and ("test" in path.name.lower() or "spec" in path.name.lower())),
        "docs": docs,
        "agent_entrypoints": agent_entrypoints(root),
        "cleanup_signals": cleanup_signals(root, lockfiles),
        "broken_markdown_links": broken_links(root),
    }


def markdown(report: dict[str, Any]) -> str:
    lines = ["# Codebase inspection", "", f"Root: `{report['root']}`", ""]
    for key in ("stacks", "manifests", "lockfiles", "version_pins", "env_examples", "containers", "ci"):
        values = report[key]
        rendered = ", ".join(f"`{value}`" for value in values) if values else "none detected"
        lines.extend([f"## {key.replace('_', ' ').title()}", "", rendered, ""])
    lines.extend(["## Commands", ""])
    lines.extend([f"- `{name}`: `{command}`" for name, command in report["commands"].items()] or ["- none detected"])
    lines.extend(["", "## Documentation owners", ""])
    lines.extend(f"- {name}: {'present' if present else 'missing'}" for name, present in report["docs"].items())
    lines.extend(["", "## Coding-agent entrypoints", ""])
    lines.extend(f"- `{name}`: {'present' if report['agent_entrypoints'][name] else 'missing'}" for name in ("AGENTS.md", "CLAUDE.md"))
    lines.append(f"- shared-content status: {report['agent_entrypoints']['sync']}")
    lines.extend(
        f"- `{name}` source tree: {'present' if report['agent_entrypoints']['source_tree'][name] else 'missing'}"
        for name in ("AGENTS.md", "CLAUDE.md")
    )
    lines.extend(
        f"- `{name}` docs coverage: {'complete' if report['agent_entrypoints']['docs_coverage'][name] else 'incomplete'}"
        for name in ("AGENTS.md", "CLAUDE.md")
    )
    lines.extend(
        f"- `{name}` canonical core: {'exact' if report['agent_entrypoints']['canonical_core'][name] else 'missing or modified'}"
        for name in ("AGENTS.md", "CLAUDE.md")
    )
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
