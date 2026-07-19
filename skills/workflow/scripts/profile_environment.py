#!/usr/bin/env python3
"""Write sanitized global machine and repository workflow profiles."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


TOOLS = {
    "git": ["git", "--version"],
    "python3": ["python3", "--version"],
    "node": ["node", "--version"],
    "pnpm": ["pnpm", "--version"],
    "npm": ["npm", "--version"],
    "uv": ["uv", "--version"],
    "docker": ["docker", "--version"],
    "cargo": ["cargo", "--version"],
}
PROFILE_SCHEMA = 1


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_run(command: list[str], cwd: Path | None = None, timeout: int = 5) -> tuple[int, str]:
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "LANG": "C",
        "LC_ALL": "C",
    }
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""
    output = " ".join(line.strip() for line in result.stdout.splitlines() if line.strip())
    home = str(Path.home())
    return result.returncode, output.replace(home, "~")[:240]


def tool_profile() -> dict[str, dict[str, Any]]:
    profile: dict[str, dict[str, Any]] = {}
    for name, command in TOOLS.items():
        path = shutil.which(command[0])
        if path is None:
            profile[name] = {"available": False, "version": None}
            continue
        code, output = safe_run(command)
        profile[name] = {"available": code == 0, "version": output or None}
    return profile


def total_memory_bytes() -> int | None:
    if platform.system() == "Darwin":
        code, output = safe_run(["sysctl", "-n", "hw.memsize"])
        if code == 0 and output.isdigit():
            return int(output)
    if platform.system() == "Linux":
        try:
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            return None
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        physical_pages = os.sysconf("SC_PHYS_PAGES")
        if isinstance(page_size, int) and isinstance(physical_pages, int) and page_size > 0 and physical_pages > 0:
            return page_size * physical_pages
    except (OSError, ValueError):
        pass
    return None


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def machine_profile(repo: Path) -> dict[str, Any]:
    tools = tool_profile()
    disk = shutil.disk_usage(repo)
    core = {
        "system": platform.system(),
        "release": platform.release(),
        "architecture": platform.machine(),
        "logical_cpu_count": os.cpu_count(),
        "memory_total_bytes": total_memory_bytes(),
        "disk_free_bytes": disk.free,
        "tools": tools,
    }
    return {
        "schema_version": PROFILE_SCHEMA,
        "generated_at": now_utc(),
        "fingerprint": stable_hash({key: value for key, value in core.items() if key != "disk_free_bytes"}),
        "sanitization": {
            "environment_values": "excluded",
            "credentials": "excluded",
            "process_arguments": "excluded",
            "hardware_serials": "excluded",
            "arbitrary_user_files": "excluded",
        },
        **core,
    }


def git_output(repo: Path, arguments: list[str]) -> tuple[int, str]:
    return safe_run(["git", *arguments], cwd=repo, timeout=10)


def repository_profile(repo: Path, machine_fingerprint: str) -> dict[str, Any]:
    git_code, git_root = git_output(repo, ["rev-parse", "--show-toplevel"])
    is_git = git_code == 0
    branch = head = None
    dirty_entries = untracked_entries = worktree_count = 0
    tracked_count = tracked_bytes = 0
    if is_git:
        _, branch_output = git_output(repo, ["symbolic-ref", "--quiet", "--short", "HEAD"])
        _, head_output = git_output(repo, ["rev-parse", "HEAD"])
        _, status_output = git_output(repo, ["status", "--porcelain=v1", "--untracked-files=normal"])
        _, worktree_output = git_output(repo, ["worktree", "list", "--porcelain"])
        branch = branch_output or "detached"
        head = head_output or None
        status_lines = [line for line in status_output.split(" ") if line]
        # safe_run flattens lines, so use a direct NUL-safe command for tracked paths below and
        # count porcelain records through a second command without persisting their path text.
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain=v1", "-z", "--untracked-files=normal"],
                cwd=str(repo),
                env={"PATH": os.environ.get("PATH", ""), "LANG": "C", "LC_ALL": "C"},
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
            records = [record for record in result.stdout.split(b"\0") if record]
            dirty_entries = len(records)
            untracked_entries = sum(record.startswith(b"??") for record in records)
        except (OSError, subprocess.TimeoutExpired):
            dirty_entries = len(status_lines)
        worktree_count = worktree_output.count("worktree ")
        try:
            result = subprocess.run(
                ["git", "ls-files", "-z"],
                cwd=str(repo),
                env={"PATH": os.environ.get("PATH", ""), "LANG": "C", "LC_ALL": "C"},
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
            )
            paths = [Path(os.fsdecode(item)) for item in result.stdout.split(b"\0") if item]
            tracked_count = len(paths)
            for relative in paths:
                try:
                    candidate = repo / relative
                    if candidate.is_file() and not candidate.is_symlink():
                        tracked_bytes += candidate.stat().st_size
                except OSError:
                    continue
        except (OSError, subprocess.TimeoutExpired):
            pass

    route_candidates = [
        "AGENTS.md",
        "CLAUDE.md",
        "docs/README.md",
        "docs/CONVENTIONS.md",
        "docs/TESTING.md",
        "docs/DEBUG.md",
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
    ]
    routing_files = [path for path in route_candidates if (repo / path).is_file()]
    lockfiles = [
        path
        for path in ("pnpm-lock.yaml", "package-lock.json", "yarn.lock", "uv.lock", "poetry.lock", "Cargo.lock")
        if (repo / path).is_file()
    ]
    core = {
        "repository_name": repo.name,
        "is_git_repository": is_git,
        "branch": branch,
        "head": head,
        "dirty_entries": dirty_entries,
        "untracked_entries": untracked_entries,
        "worktree_count": worktree_count,
        "tracked_file_count": tracked_count,
        "tracked_file_bytes": tracked_bytes,
        "routing_files": routing_files,
        "lockfiles": lockfiles,
        "machine_fingerprint": machine_fingerprint,
    }
    return {
        "schema_version": PROFILE_SCHEMA,
        "generated_at": now_utc(),
        "fingerprint": stable_hash(core),
        **core,
    }


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def is_fresh(profile: dict[str, Any] | None, fingerprint: str, max_age_days: int) -> bool:
    if not profile or profile.get("fingerprint") != fingerprint:
        return False
    try:
        generated = dt.datetime.fromisoformat(str(profile["generated_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return False
    return dt.datetime.now(dt.timezone.utc) - generated <= dt.timedelta(days=max_age_days)


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Repository root to profile")
    parser.add_argument("--global-output", help="Override global machine profile path")
    parser.add_argument("--repo-output", help="Override repository overlay path")
    parser.add_argument("--max-age-days", type=int, default=7)
    parser.add_argument("--no-write", action="store_true", help="Print profiles without writing them")
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        parser.error(f"repository path is not a directory: {repo}")
    if args.max_age_days < 0:
        parser.error("--max-age-days must be non-negative")

    global_path = Path(args.global_output).expanduser() if args.global_output else Path.home() / ".codex" / "workflow-profiles" / "machine.json"
    repo_path = Path(args.repo_output).expanduser() if args.repo_output else repo / ".codex" / "workflow-profile.json"
    machine = machine_profile(repo)
    overlay = repository_profile(repo, machine["fingerprint"])
    machine_reused = is_fresh(load_json(global_path), machine["fingerprint"], args.max_age_days)
    overlay_reused = is_fresh(load_json(repo_path), overlay["fingerprint"], args.max_age_days)

    if not args.no_write:
        if not machine_reused:
            atomic_write(global_path, machine)
        if not overlay_reused:
            atomic_write(repo_path, overlay)

    result = {
        "global_profile": {"path": str(global_path), "reused": machine_reused, "profile": load_json(global_path) if machine_reused else machine},
        "repository_overlay": {"path": str(repo_path), "reused": overlay_reused, "profile": load_json(repo_path) if overlay_reused else overlay},
        "written": not args.no_write,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
