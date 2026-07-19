#!/usr/bin/env python3
"""Inspect registered Git worktrees and run one command across selected paths."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any


def git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=text,
    )
    if result.returncode != 0:
        stderr = result.stderr if text else result.stderr.decode(errors="replace")
        raise RuntimeError(stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def registered_worktrees(repo: Path) -> list[dict[str, str]]:
    raw = git(repo, "worktree", "list", "--porcelain", "-z", text=False)
    assert isinstance(raw, bytes)
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for field in raw.split(b"\0"):
        if not field:
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = field.decode(errors="surrogateescape").partition(" ")
        current[key] = value
    if current:
        records.append(current)
    return records


def worktree_details(entry: dict[str, str]) -> dict[str, Any]:
    path = Path(entry["worktree"]).resolve()
    branch_ref = entry.get("branch", "")
    branch = branch_ref.removeprefix("refs/heads/") or "(detached)"
    missing = not path.is_dir()
    if missing:
        dirty: bool | None = None
        upstream = "-"
    else:
        status = git(path, "status", "--porcelain")
        assert isinstance(status, str)
        dirty = bool(status)
        upstream_result = subprocess.run(
            [
                "git",
                "-C",
                str(path),
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{upstream}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        upstream = upstream_result.stdout.strip() if upstream_result.returncode == 0 else "-"
    return {
        "path": str(path),
        "branch": branch,
        "head": entry.get("HEAD", "-"),
        "upstream": upstream,
        "dirty": dirty,
        "missing": missing,
        "locked": "locked" in entry,
        "prunable": "prunable" in entry,
    }


def print_inventory(items: list[dict[str, Any]], as_json: bool) -> None:
    if as_json:
        print(json.dumps(items, indent=2))
        return
    headers = ("PATH", "BRANCH", "HEAD", "UPSTREAM", "DIRTY", "FLAGS")
    rows = []
    for item in items:
        flags = ",".join(name for name in ("missing", "locked", "prunable") if item[name]) or "-"
        dirty = "unknown" if item["dirty"] is None else "yes" if item["dirty"] else "no"
        rows.append(
            (
                item["path"],
                item["branch"],
                item["head"][:12],
                item["upstream"],
                dirty,
                flags,
            )
        )
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))]
    print("  ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    for row in rows:
        print("  ".join(row[i].ljust(widths[i]) for i in range(len(headers))))


def parse_env(values: list[str]) -> dict[str, str]:
    env: dict[str, str] = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"invalid --env value: {value!r}; expected KEY=VALUE")
        env[key] = item
    return env


def safe_name(branch: str, path: Path) -> str:
    source = path.name if branch == "(detached)" else branch
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", source).strip("-") or "worktree"


async def stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except asyncio.TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()


async def run_one(
    slot: int,
    item: dict[str, Any],
    command: list[str],
    extra_env: dict[str, str],
    port_step: int,
    log_dir: Path,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    path = Path(item["path"])
    name = safe_name(item["branch"], path)
    log_path = log_dir / f"{slot:02d}-{name}.log"
    async with semaphore:
        env = os.environ.copy()
        env.update(extra_env)
        env.update(
            {
                "WORKTREE_SLOT": str(slot),
                "WORKTREE_NAME": name,
                "WORKTREE_PORT_OFFSET": str(slot * port_step),
            }
        )
        print(f"START slot={slot} path={path} log={log_path}", flush=True)
        with log_path.open("wb") as log_file:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=path,
                env=env,
                stdout=log_file,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                return_code = await process.wait()
            except asyncio.CancelledError:
                await stop_process(process)
                raise
        print(f"DONE  slot={slot} exit={return_code} path={path}", flush=True)
        return {
            "slot": slot,
            "path": str(path),
            "branch": item["branch"],
            "head": item["head"],
            "exit": return_code,
            "log": str(log_path),
        }


async def run_matrix(args: argparse.Namespace, items: list[dict[str, Any]]) -> int:
    started_at = datetime.now(timezone.utc).isoformat()
    log_dir = Path(args.log_dir).resolve() if args.log_dir else Path(
        tempfile.mkdtemp(prefix="worktree-")
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    print(f"COMMAND {shlex.join(args.command)}")
    print(f"LOG_DIR {log_dir}")
    semaphore = asyncio.Semaphore(args.max_parallel)
    tasks = [
        asyncio.create_task(
            run_one(slot, item, args.command, args.extra_env, args.port_step, log_dir, semaphore)
        )
        for slot, item in enumerate(items)
    ]
    try:
        results = await asyncio.gather(*tasks)
    except (KeyboardInterrupt, asyncio.CancelledError):
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        print("Interrupted; child process groups stopped.", file=sys.stderr)
        return 130
    summary_path = log_dir / "summary.json"
    summary = {
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": args.command,
        "results": results,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"SUMMARY {summary_path}")
    return 1 if any(result["exit"] != 0 for result in results) else 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subparsers = root.add_subparsers(dest="action", required=True)

    inventory = subparsers.add_parser("inventory", help="show registered worktree state")
    inventory.add_argument("--repo", default=".", help="path inside the repository")
    inventory.add_argument("--json", action="store_true", help="emit JSON")

    run = subparsers.add_parser("run", help="run one command in selected worktrees")
    run.add_argument("--repo", default=".", help="path inside the repository")
    run.add_argument("--worktree", action="append", required=True, help="registered worktree path")
    run.add_argument("--max-parallel", type=int, default=2)
    run.add_argument("--port-step", type=int, default=100)
    run.add_argument("--log-dir", help="output directory; defaults to a new system temp directory")
    run.add_argument("--env", dest="env_values", action="append", default=[], help="shared KEY=VALUE")
    run.add_argument("command", nargs=argparse.REMAINDER)
    return root


def main() -> int:
    args = parser().parse_args()
    repo = Path(args.repo).resolve()
    try:
        entries = registered_worktrees(repo)
        items = [worktree_details(entry) for entry in entries]
        if args.action == "inventory":
            print_inventory(items, args.json)
            return 0

        if args.max_parallel < 1 or args.port_step < 0:
            raise ValueError("--max-parallel must be positive and --port-step must be non-negative")
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not command:
            raise ValueError("provide a command after --")
        args.command = command
        args.extra_env = parse_env(args.env_values)

        registered = {str(Path(item["path"]).resolve()): item for item in items}
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for value in args.worktree:
            path = str(Path(value).resolve())
            if path not in registered:
                raise ValueError(f"not a registered worktree: {path}")
            if path in seen:
                raise ValueError(f"duplicate worktree: {path}")
            if registered[path]["missing"]:
                raise ValueError(f"registered worktree path is missing: {path}")
            seen.add(path)
            selected.append(registered[path])
        return asyncio.run(run_matrix(args, selected))
    except (RuntimeError, ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
