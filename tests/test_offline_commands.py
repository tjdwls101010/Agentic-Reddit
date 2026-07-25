"""Subprocess guards for browser-free offline commands."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SITE_CUSTOMIZE = r"""
import asyncio
import atexit
import builtins
import subprocess
import sys

assert "scrapling" not in sys.modules
real_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name == "scrapling" or name.startswith("scrapling."):
        raise AssertionError("offline command imported scrapling")
    return real_import(name, *args, **kwargs)

def browser_launch(*args, **kwargs):
    raise AssertionError("offline command attempted to launch a browser")

def confirm_offline_import_state():
    assert "scrapling" not in sys.modules
    print("offline import guard passed", file=sys.stderr)

builtins.__import__ = guarded_import
subprocess.Popen = browser_launch
asyncio.create_subprocess_exec = browser_launch
atexit.register(confirm_offline_import_state)
"""


@pytest.mark.parametrize(
    "argv",
    [
        ["--version"],
        ["--help"],
        ["catalog"],
        ["catalog", "--json"],
        ["schema"],
        ["schema", "--json"],
    ],
)
def test_offline_commands_do_not_import_scrapling_or_launch_browser(
    argv: list[str], tmp_path: Path
) -> None:
    project = Path(__file__).resolve().parents[1]
    (tmp_path / "sitecustomize.py").write_text(_SITE_CUSTOMIZE, encoding="utf-8")
    environment = os.environ.copy()
    python_path = [str(tmp_path), str(project / "src")]
    if existing := environment.get("PYTHONPATH"):
        python_path.append(existing)
    environment["PYTHONPATH"] = os.pathsep.join(python_path)
    completed = subprocess.run(
        [sys.executable, "-m", "agentic_reddit", *argv],
        cwd=project,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "offline import guard passed" in completed.stderr
    if argv[0] in {"catalog", "schema"}:
        payload = json.loads(completed.stdout)
        assert isinstance(payload, dict)
    elif argv == ["--version"]:
        assert completed.stdout.startswith("agentic-reddit ")
    else:
        assert "usage: agentic-reddit" in completed.stdout
