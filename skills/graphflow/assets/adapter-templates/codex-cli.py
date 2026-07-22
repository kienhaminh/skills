#!/usr/bin/env python3
"""Optional Graphflow adapter for the Codex CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    request = json.load(sys.stdin)
    binary = os.environ.get("GRAPHFLOW_CODEX_BIN") or shutil.which("codex") or "codex"
    with tempfile.TemporaryDirectory(prefix="graphflow-codex-") as directory:
        final = Path(directory) / "result.json"
        command = [
            binary,
            "exec",
            "--json",
            "--output-last-message",
            str(final),
            "--cd",
            str(request["cwd"]),
            "--sandbox",
            str(request["sandbox"]),
            "--config",
            'approval_policy="never"',
            "--ephemeral",
        ]
        if request.get("output_schema"):
            command.extend(["--output-schema", str(request["output_schema"])])
        if request.get("model"):
            command.extend(["--model", str(request["model"])])
        if request.get("reasoning_effort"):
            command.extend(["--config", f"model_reasoning_effort={request['reasoning_effort']}"])
        command.append("-")
        completed = subprocess.run(
            command,
            input=str(request.get("prompt", "")),
            cwd=str(request["cwd"]),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode or not final.is_file():
            return completed.returncode or 1
        value = json.loads(final.read_text(encoding="utf-8"))
        json.dump(value, sys.stdout, sort_keys=True, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
