#!/usr/bin/env python3
"""Build a checkout-derived, per-file source index and ranked task read set."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import posixpath
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Optional


IGNORED = {
    ".claude", ".codex", ".git", ".next", ".turbo", ".venv",
    "build", "coverage", "dist", "node_modules", "target", "vendor",
}
LANGUAGES = {
    ".c": "c", ".cc": "cpp", ".cpp": "cpp", ".cs": "csharp",
    ".go": "go", ".h": "c", ".hpp": "cpp", ".java": "java",
    ".cjs": "javascript", ".js": "javascript", ".jsx": "javascript",
    ".mjs": "javascript", ".kt": "kotlin",
    ".kts": "kotlin", ".m": "objective-c", ".mm": "objective-cpp",
    ".php": "php", ".py": "python", ".rb": "ruby", ".rs": "rust",
    ".scala": "scala", ".swift": "swift", ".cts": "typescript",
    ".mts": "typescript", ".ts": "typescript",
    ".tsx": "typescript", ".vue": "vue", ".svelte": "svelte",
}
STOPWORDS = {
    "app", "apps", "src", "source", "lib", "libs", "packages", "pkg",
    "index", "main", "the", "and", "from", "with", "this", "that",
}
IMPORT_PATTERNS = {
    "javascript": re.compile(
        r"(?:import|export)\s+(?:type\s+)?(?:[\s\S]*?\s+from\s+)?[\"']([^\"']+)[\"']|"
        r"(?:require|import)\s*\(\s*[\"']([^\"']+)[\"']\s*\)"
    ),
    "typescript": re.compile(
        r"(?:import|export)\s+(?:type\s+)?(?:[\s\S]*?\s+from\s+)?[\"']([^\"']+)[\"']|"
        r"(?:require|import)\s*\(\s*[\"']([^\"']+)[\"']\s*\)"
    ),
    "go": re.compile(r"^\s*(?:import\s+)?[\"`]([^\"`]+)[\"`]", re.MULTILINE),
    "rust": re.compile(r"^\s*(?:use|mod)\s+([^;]+);", re.MULTILINE),
    "swift": re.compile(r"^\s*import\s+([A-Za-z_][\w.]*)", re.MULTILINE),
    "java": re.compile(r"^\s*import\s+(?:static\s+)?([^;]+);", re.MULTILINE),
    "kotlin": re.compile(r"^\s*import\s+([^;\s]+)", re.MULTILINE),
}
SYMBOL_PATTERNS = {
    "javascript": re.compile(
        r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?"
        r"(class|function|const|let|var)\s+([A-Za-z_$][\w$]*)",
        re.MULTILINE,
    ),
    "typescript": re.compile(
        r"^\s*(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:async\s+)?"
        r"(class|function|const|let|var|interface|type|enum|namespace)\s+([A-Za-z_$][\w$]*)",
        re.MULTILINE,
    ),
    "go": re.compile(r"^\s*(func|type|var|const)\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)", re.MULTILINE),
    "rust": re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(fn|struct|enum|trait|type|const|static|mod)\s+([A-Za-z_]\w*)", re.MULTILINE),
    "swift": re.compile(r"^\s*(?:public\s+|internal\s+|private\s+|open\s+)?(class|struct|enum|protocol|actor|func|typealias)\s+([A-Za-z_]\w*)", re.MULTILINE),
    "java": re.compile(r"^\s*(?:public\s+|protected\s+|private\s+|abstract\s+|final\s+)*(class|interface|enum|record)\s+([A-Za-z_]\w*)", re.MULTILINE),
    "kotlin": re.compile(r"^\s*(?:public\s+|internal\s+|private\s+)?(class|interface|object|enum\s+class|fun|typealias)\s+([A-Za-z_]\w*)", re.MULTILINE),
    "ruby": re.compile(r"^\s*(class|module|def)\s+([A-Za-z_]\w*[!?=]?)", re.MULTILINE),
    "php": re.compile(r"^\s*(?:final\s+|abstract\s+)?(class|interface|trait|enum|function)\s+([A-Za-z_]\w*)", re.MULTILINE),
    "csharp": re.compile(r"^\s*(?:public\s+|internal\s+|private\s+|protected\s+|static\s+|abstract\s+|sealed\s+)*(class|interface|struct|record|enum)\s+([A-Za-z_]\w*)", re.MULTILINE),
}


def source_files(root: Path) -> Iterable[Path]:
    for directory, names, files in os.walk(root):
        names[:] = sorted(name for name in names if name not in IGNORED)
        base = Path(directory)
        for name in sorted(files):
            path = base / name
            if path.suffix.lower() in LANGUAGES:
                yield path


def words(value: str) -> list[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return [
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]+", value)
        if token.lower() not in STOPWORDS
    ]


def role(path: Path) -> str:
    lowered = "/".join(path.parts).lower()
    name = path.stem.lower()
    if re.search(r"(^|[._-])(test|spec|tests)([._-]|$)", path.name.lower()) or "/tests/" in f"/{lowered}/":
        return "test"
    if "migration" in lowered:
        return "migration"
    if name in {"main", "server", "worker", "app", "cli", "manage"}:
        return "entrypoint"
    for marker, label in (
        ("controller", "controller"), ("router", "router"), ("route", "route"),
        ("service", "service"), ("repository", "repository"), ("schema", "schema"),
        ("model", "model"), ("entity", "model"), ("config", "config"),
        ("component", "component"), ("page", "page"), ("view", "view"),
        ("guard", "guard"), ("module", "module"), ("contract", "contract"),
        ("dto", "contract"), ("tool", "tool"), ("util", "utility"),
        ("helper", "utility"),
    ):
        if marker in name or f"/{marker}" in f"/{lowered}":
            return label
    return "source"


def python_facts(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    symbols: list[dict[str, Any]] = []
    imports: list[str] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return symbols, imports
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append({"name": node.name, "kind": "function", "line": node.lineno})
        elif isinstance(node, ast.ClassDef):
            symbols.append({"name": node.name, "kind": "class", "line": node.lineno})
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            imports.append(prefix + (node.module or ""))
    return symbols, imports


def regex_facts(text: str, language: str) -> tuple[list[dict[str, Any]], list[str]]:
    symbols: list[dict[str, Any]] = []
    pattern = SYMBOL_PATTERNS.get(language)
    if pattern:
        for match in pattern.finditer(text):
            symbols.append({
                "name": match.group(2),
                "kind": match.group(1).replace(" ", "_"),
                "line": text.count("\n", 0, match.start()) + 1,
            })
    imports: list[str] = []
    import_pattern = IMPORT_PATTERNS.get(language)
    if import_pattern:
        for match in import_pattern.finditer(text):
            value = next((group for group in match.groups() if group), None)
            if value:
                imports.append(value.strip())
    return symbols, imports


def record(root: Path, path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    language = LANGUAGES[path.suffix.lower()]
    symbols, imports = python_facts(text) if language == "python" else regex_facts(text, language)
    keyword_counts = Counter(words(str(path.relative_to(root))))
    keyword_counts.update(words(text))
    for symbol in symbols:
        keyword_counts.update(words(symbol["name"]))
    return {
        "path": str(path.relative_to(root)),
        "language": language,
        "role": role(path.relative_to(root)),
        "bytes": len(raw),
        "lines": text.count("\n") + (0 if not text or text.endswith("\n") else 1),
        "sha256": hashlib.sha256(raw).hexdigest()[:16],
        "keywords": [word for word, _ in keyword_counts.most_common(80)],
        "symbols": symbols[:80],
        "imports": sorted(set(imports))[:120],
        "referenced_by": [],
        "related_tests": [],
    }


def score(item: dict[str, Any], query: str, inbound: int) -> float:
    tokens = words(query)
    if not tokens:
        base = 3 if item["role"] == "entrypoint" else 0
        return base + math.log2(inbound + 1)
    path = item["path"].lower()
    symbol_text = " ".join(symbol["name"] for symbol in item["symbols"]).lower()
    keywords = set(item["keywords"])
    imports = " ".join(item["imports"]).lower()
    value = 0.0
    for token in tokens:
        value += 10 if token in path else 0
        value += 8 if token in symbol_text else 0
        value += 5 if token in keywords else 0
        value += 3 if token in imports else 0
    if query.lower() in f"{path} {symbol_text}":
        value += 12
    if item["role"] in {"entrypoint", "test"} and value:
        value += 2
    return value + min(4.0, math.log2(inbound + 1))


def resolve_import(source: str, imported: str, paths: set[str], unique_stems: dict[str, str]) -> Optional[str]:
    if imported.startswith("."):
        base = posixpath.normpath(posixpath.join(posixpath.dirname(source), imported))
        candidates = [base]
        for suffix in LANGUAGES:
            candidates.extend((base + suffix, posixpath.join(base, "index" + suffix)))
        for candidate in candidates:
            if candidate in paths:
                return candidate
    stem = Path(imported).stem
    return unique_stems.get(stem)


def normalized_test_stem(path: str) -> str:
    stem = Path(path).stem.lower()
    return re.sub(r"(?:[._-](?:int|e2e|unit))?[._-](?:spec|test)$", "", stem)


def enrich_graph(records: list[dict[str, Any]]) -> None:
    paths = {item["path"] for item in records}
    stem_counts = Counter(Path(path).stem for path in paths)
    unique_stems = {Path(path).stem: path for path in paths if stem_counts[Path(path).stem] == 1}
    by_path = {item["path"]: item for item in records}
    for item in records:
        for imported in item["imports"]:
            target = resolve_import(item["path"], imported, paths, unique_stems)
            if target:
                by_path[target]["referenced_by"].append(item["path"])
    tests = [item for item in records if item["role"] == "test"]
    for item in records:
        if item["role"] == "test":
            continue
        stem = normalized_test_stem(item["path"])
        related = {
            test["path"]
            for test in tests
            if normalized_test_stem(test["path"]) == stem
            or item["path"] in {
                resolve_import(test["path"], imported, paths, unique_stems)
                for imported in test["imports"]
            }
        }
        item["related_tests"] = sorted(related)
    for item in records:
        item["referenced_by"] = sorted(set(item["referenced_by"]))


def inbound_counts(records: list[dict[str, Any]]) -> Counter[str]:
    return Counter({item["path"]: len(item["referenced_by"]) for item in records})


def percentile(values: list[int], fraction: float) -> int:
    """Return a nearest-rank percentile for a non-empty sequence."""
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


def convention_stats(records: list[dict[str, Any]], limit: int, max_lines: int) -> str:
    by_language: dict[str, list[int]] = {}
    by_role: dict[str, list[int]] = {}
    for item in records:
        by_language.setdefault(item["language"], []).append(item["lines"])
        by_role.setdefault(item["role"], []).append(item["lines"])

    lines = [
        "# Convention baseline",
        "",
        "Physical line counts are screening signals, not automatic split decisions.",
        "Generated, vendored, migration, fixture, snapshot, and declarative files require project-specific exclusions.",
        "",
        "## Size distribution",
        "",
        "| Language | Files | Median | p90 | p95 | Max |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for language, values in sorted(by_language.items()):
        lines.append(
            f"| {language} | {len(values)} | {percentile(values, 0.5)} | "
            f"{percentile(values, 0.9)} | {percentile(values, 0.95)} | {max(values)} |"
        )

    lines.extend([
        "",
        "## Roles",
        "",
        "| Role | Files | Median | p90 | p95 | Max |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for name, values in sorted(by_role.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        lines.append(
            f"| {name} | {len(values)} | {percentile(values, 0.5)} | "
            f"{percentile(values, 0.9)} | {percentile(values, 0.95)} | {max(values)} |"
        )

    largest = sorted(records, key=lambda item: (-item["lines"], item["path"]))[:limit]
    lines.extend([
        "",
        "## Largest source files",
        "",
        "| Path | Role | Language | Lines | Symbols |",
        "| --- | --- | --- | ---: | ---: |",
    ])
    for item in largest:
        lines.append(
            f"| `{item['path']}` | {item['role']} | {item['language']} | "
            f"{item['lines']} | {len(item['symbols'])} |"
        )

    duplicate_groups: dict[tuple[str, int], list[str]] = {}
    for item in records:
        if item["bytes"] >= 80:
            duplicate_groups.setdefault((item["sha256"], item["bytes"]), []).append(item["path"])
    duplicates = [paths for paths in duplicate_groups.values() if len(paths) > 1]
    duplicates.sort(key=lambda paths: (-len(paths), paths))
    lines.extend(["", "## Exact-content duplicate candidates", ""])
    if duplicates:
        for paths in duplicates[:limit]:
            lines.append("- " + ", ".join(f"`{path}`" for path in paths))
    else:
        lines.append("None detected among supported source files of at least 80 bytes.")

    if max_lines:
        over_budget = [item for item in records if item["lines"] > max_lines]
        over_budget.sort(key=lambda item: (-item["lines"], item["path"]))
        lines.extend([
            "",
            f"## Files above the supplied {max_lines}-line review budget",
            "",
        ])
        if over_budget:
            for item in over_budget[:limit]:
                lines.append(f"- `{item['path']}` — {item['lines']} lines")
        else:
            lines.append("None.")
        if len(over_budget) > limit:
            lines.append(f"- … {len(over_budget) - limit} more")

    lines.extend([
        "",
        f"Indexed source files: {len(records)}.",
        "Add a language-native analyzer for logical LOC, complexity, dependency cycles, coupling, and near-clone detection.",
    ])
    return "\n".join(lines)


def markdown(records: list[dict[str, Any]], query: str, limit: int) -> str:
    inbound = inbound_counts(records)
    ranked = sorted(
        records,
        key=lambda item: (-score(item, query, inbound[item["path"]]), item["path"]),
    )
    if query:
        ranked = [item for item in ranked if score(item, query, inbound[item["path"]]) > 0]
    ranked = ranked[:limit]
    lines = ["# Ranked source read set", "", f"Query: `{query or '<global map>'}`", ""]
    lines.append("| Path | Role | Lines | Symbols | Leading keywords |")
    lines.append("| --- | --- | ---: | --- | --- |")
    for item in ranked:
        symbols = ", ".join(symbol["name"] for symbol in item["symbols"][:8]) or "—"
        keywords = ", ".join(item["keywords"][:10]) or "—"
        lines.append(f"| `{item['path']}` | {item['role']} | {item['lines']} | {symbols} | {keywords} |")
    lines.extend(["", f"Indexed source files: {len(records)}. Returned: {len(ranked)}."])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--format", choices=("ndjson", "json", "markdown", "stats"), default="markdown")
    parser.add_argument("--max-lines", type=int, default=0, help="optional review budget shown by stats")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")
    if args.limit < 1:
        parser.error("--limit must be positive")
    if args.max_lines < 0:
        parser.error("--max-lines must be zero or positive")
    records = [record(root, path) for path in source_files(root)]
    enrich_graph(records)
    if args.format == "ndjson":
        rendered = "\n".join(json.dumps(item, ensure_ascii=False) for item in records)
    elif args.format == "json":
        rendered = json.dumps(records, ensure_ascii=False, indent=2)
    elif args.format == "markdown":
        rendered = markdown(records, args.query, args.limit)
    else:
        rendered = convention_stats(records, args.limit, args.max_lines)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
