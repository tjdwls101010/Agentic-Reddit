#!/usr/bin/env python3
"""Fail when a release tag, project metadata, and source version disagree.

Usage: check_tag_version.py <tag-name, e.g. "v0.1.0">
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def source_version(path: Path) -> str:
    """Read a statically assigned ``__version__`` without importing the package."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            targets = statement.targets
        elif isinstance(statement, ast.AnnAssign):
            targets = [statement.target]
        else:
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in targets
        ):
            continue
        if isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
            return statement.value.value
        break
    raise ValueError(f"{path} must define __version__ as a static string")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: check_tag_version.py <tag-name>", file=sys.stderr)
        return 1

    tag_name = args[0]
    tag_version = tag_name.removeprefix("v")
    try:
        with (PROJECT_ROOT / "pyproject.toml").open("rb") as stream:
            pyproject_version = tomllib.load(stream)["project"]["version"]
        if not isinstance(pyproject_version, str):
            raise ValueError("pyproject version must be a string")
        package_version = source_version(PROJECT_ROOT / "src/agentic_reddit/__init__.py")
    except (KeyError, OSError, SyntaxError, ValueError, TypeError):
        print(
            "::error::could not read package versions; check pyproject.toml "
            "[project].version and src/agentic_reddit/__init__.py __version__",
            file=sys.stderr,
        )
        return 1

    if tag_version != pyproject_version or pyproject_version != package_version:
        print(
            "::error::release versions do not match across tag, pyproject.toml, "
            "and agentic_reddit.__version__",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: tag {tag_name!r} matches pyproject.toml and "
        f"agentic_reddit.__version__ ({pyproject_version!r})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
