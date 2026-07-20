#!/usr/bin/env python3
"""Serve, inspect, and stop an owned loopback workflow dashboard."""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import http.server
import json
import os
import signal
import shlex
import socket
import subprocess
import sys
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import progress_state
import workspace_manager
import checkout_guard


HOST = "127.0.0.1"
METADATA_NAME = ".dashboard-server.json"
ALLOWED_PATHS = {
    "/graph.json",
    "/runtime.json",
    "/requests.json",
    "/progress.json",
    "/workspaces.json",
    "/checkout.json",
    "/memory/state.json",
    "/dashboard/",
    "/dashboard/index.html",
    "/dashboard/app.js",
    "/dashboard/styles.css",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_metadata(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def read_metadata(root: Path) -> dict[str, Any] | None:
    try:
        value = json.loads((root / METADATA_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def process_alive(pid: int) -> bool | None:
    try:
        os.kill(pid, 0)
    except PermissionError:
        return None
    except (OSError, ValueError):
        return False
    return True


def command_owns_root(command: str, root: Path) -> bool:
    try:
        tokens = shlex.split(command)
        serve_index = tokens.index("serve")
        command_root = Path(tokens[serve_index + 1]).expanduser().resolve()
    except (ValueError, IndexError):
        return False
    return any(Path(token).name == Path(__file__).name for token in tokens) and command_root == root.resolve()


def owned_process(pid: int, root: Path) -> bool:
    if process_alive(pid) is False:
        return False
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return command_owns_root(result.stdout, root)


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib API
        path = urllib.parse.urlsplit(self.path).path
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/dashboard/")
            self.end_headers()
            return
        if path not in ALLOWED_PATHS:
            self.send_error(404, "Not found")
            return
        if path == "/requests.json":
            root = Path(self.directory).resolve()
            payload = {"schema_version": 1, "requests": confirmation_projection(root)}
            encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if path in {"/progress.json", "/workspaces.json"}:
            root = Path(self.directory).resolve()
            try:
                items = progress_state.projection(root) if path == "/progress.json" else workspace_manager.projection(root)
            except ValueError:
                items = []
            key = "progress" if path == "/progress.json" else "workspaces"
            encoded = json.dumps({"schema_version": 1, key: items}, sort_keys=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if path == "/checkout.json":
            root = Path(self.directory).resolve()
            try:
                payload = checkout_guard.projection(root)
            except ValueError:
                payload = checkout_guard.default_config()
            encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        super().end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(f"dashboard {self.address_string()} {format % args}\n")


def confirmation_projection(root: Path) -> list[dict[str, Any]]:
    directory = root / "runtime" / "requests"
    if not directory.is_dir():
        return []
    allowed = {"request_id", "node_id", "broker", "status", "question", "alternatives", "risks", "triage", "created_at", "consumed_at", "superseded_at", "invalidated_reason"}
    projected: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            projected.append({key: value[key] for key in allowed if key in value})
    return projected


def validate_root(root: Path) -> None:
    required = [root / "graph.json", root / "runtime.json", root / "memory" / "state.json", root / "dashboard" / "index.html", root / "dashboard" / "app.js", root / "dashboard" / "styles.css"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"workflow directory is missing: {', '.join(missing)}")


def bind_server(root: Path, start: int, maximum: int) -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = functools.partial(DashboardHandler, directory=str(root))
    for port in range(start, maximum + 1):
        try:
            return http.server.ThreadingHTTPServer((HOST, port), handler), port
        except OSError:
            continue
    raise ValueError(f"no free loopback port from {start} through {maximum}")


def serve(args: argparse.Namespace) -> int:
    root = Path(args.workflow_dir).expanduser().resolve()
    validate_root(root)
    existing = read_metadata(root)
    if existing and process_alive(int(existing.get("pid", -1))) is not False:
        raise ValueError(f"dashboard already appears active with PID {existing.get('pid')}")
    server, port = bind_server(root, args.port, args.max_port)
    metadata = {
        "schema_version": 1,
        "instance_id": uuid.uuid4().hex,
        "pid": os.getpid(),
        "host": HOST,
        "port": port,
        "workflow_dir": str(root),
        "started_at": now_utc(),
        "url": f"http://{HOST}:{port}/dashboard/",
    }
    atomic_metadata(root / METADATA_NAME, metadata)
    print(json.dumps(metadata, sort_keys=True), flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        current = read_metadata(root)
        if current and current.get("instance_id") == metadata["instance_id"]:
            (root / METADATA_NAME).unlink(missing_ok=True)
    return 0


def status(args: argparse.Namespace) -> int:
    root = Path(args.workflow_dir).expanduser().resolve()
    metadata = read_metadata(root)
    if not metadata:
        print(json.dumps({"running": False, "workflow_dir": str(root)}, sort_keys=True))
        return 1
    pid = int(metadata.get("pid", -1))
    port = int(metadata.get("port", -1))
    tcp: bool | None = False
    if port > 0:
        try:
            with socket.create_connection((HOST, port), timeout=0.5):
                tcp = True
        except PermissionError:
            tcp = None
        except OSError:
            tcp = False
    visibility = process_alive(pid)
    metadata["process_visible"] = visibility
    metadata["tcp_healthy"] = tcp
    if visibility is False or tcp is False:
        metadata["running"] = False
    elif visibility is True or tcp is True:
        metadata["running"] = True
    else:
        metadata["running"] = None
    metadata["owned"] = owned_process(pid, root)
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0 if metadata["running"] is True else 1 if metadata["running"] is False else 2


def stop(args: argparse.Namespace) -> int:
    root = Path(args.workflow_dir).expanduser().resolve()
    metadata = read_metadata(root)
    if not metadata:
        print(json.dumps({"stopped": True, "reason": "no metadata"}, sort_keys=True))
        return 0
    pid = int(metadata.get("pid", -1))
    visibility = process_alive(pid)
    if visibility is False:
        (root / METADATA_NAME).unlink(missing_ok=True)
        print(json.dumps({"stopped": True, "reason": "stale metadata", "pid": pid}, sort_keys=True))
        return 0
    if not owned_process(pid, root):
        raise ValueError(f"refusing to stop PID {pid}; ownership could not be verified")
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + args.timeout
    while process_alive(pid) is not False and time.monotonic() < deadline:
        time.sleep(0.1)
    if process_alive(pid) is not False:
        raise ValueError(f"PID {pid} did not stop within {args.timeout} seconds")
    (root / METADATA_NAME).unlink(missing_ok=True)
    print(json.dumps({"stopped": True, "pid": pid}, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("workflow_dir")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--max-port", type=int, default=8799)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("workflow_dir")
    stop_parser = subparsers.add_parser("stop")
    stop_parser.add_argument("workflow_dir")
    stop_parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    try:
        if args.command == "serve":
            if not (1 <= args.port <= args.max_port <= 65535):
                raise ValueError("port range must satisfy 1 <= port <= max-port <= 65535")
            return serve(args)
        if args.command == "status":
            return status(args)
        if args.timeout <= 0:
            raise ValueError("--timeout must be positive")
        return stop(args)
    except ValueError as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
