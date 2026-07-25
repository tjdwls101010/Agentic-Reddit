"""Static supply-chain pinning contracts."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_ROOT = Path(__file__).parents[1]
_USES_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<reference>\S+)", re.MULTILINE)
_ACTION_REF_RE = re.compile(r"(?P<action>[\w.-]+/[\w.-]+)@(?P<sha>[0-9a-f]{40})\Z")
_PIP_INSTALL_RE = re.compile(
    r"^\s*run:\s*python -m pip install (?P<requirements>[^\n]+)$", re.MULTILINE
)
_EXPECTED_ACTION_PINS = {
    "actions/checkout": "11bd71901bbe5b1630ceea73d27597364c9af683",
    "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
    "actions/download-artifact": "d3f86a106a0bac45b974a628896c90dbdf5c8093",
    "pypa/gh-action-pypi-publish": "cef221092ed1bacb1cc03d23a2d87d1d172e277b",
}


def test_build_backend_is_exactly_pinned() -> None:
    pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["build-system"] == {
        "requires": ["hatchling==1.27.0"],
        "build-backend": "hatchling.build",
    }


def test_workflow_build_frontend_is_exactly_pinned() -> None:
    workflows = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((_ROOT / ".github/workflows").glob("*.y*ml"))
    )

    build_installs = [
        match["requirements"]
        for match in _PIP_INSTALL_RE.finditer(workflows)
        if re.search(r"(^|\s)build(?:==[^\s]+)?(?:\s|$)", match["requirements"])
    ]

    assert build_installs == ["build==1.5.0", "build==1.5.0"]


def test_all_third_party_workflow_actions_have_expected_full_sha_pins() -> None:
    action_pins: dict[str, set[str]] = {}
    for path in sorted((_ROOT / ".github/workflows").glob("*.y*ml")):
        for match in _USES_RE.finditer(path.read_text(encoding="utf-8")):
            action_match = _ACTION_REF_RE.fullmatch(match["reference"])
            assert action_match is not None
            action_pins.setdefault(action_match["action"], set()).add(action_match["sha"])

    assert action_pins == {action: {sha} for action, sha in _EXPECTED_ACTION_PINS.items()}
