#!/usr/bin/env python3
"""Store one JSON response from stdin in the gitignored ``scratch/`` directory.

Usage: record_fixture.py NAME < response.json

This manual-development helper performs no network or browser activity. Raw
captures can contain credentials and third-party PII; it never writes into the
committed fixture tree and refuses to overwrite a capture.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRATCH_DIR = PROJECT_ROOT / "scratch"
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
WARNING = (
    "WARNING: RAW CAPTURES MAY CONTAIN CREDENTIALS AND THIRD-PARTY PII. "
    "NEVER COMMIT, SHARE, OR COPY THEM INTO tests/fixtures/."
)
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
_DIRECTORY_MODE = 0o700
_FILE_MODE = 0o600


class CaptureError(ValueError):
    """Raised when a capture cannot be stored safely."""


def _filename(name: str) -> str:
    if (
        not _NAME_RE.fullmatch(name)
        or ".." in name
        or "/" in name
        or "\\" in name
        or Path(name).is_absolute()
    ):
        raise CaptureError("name must be a safe filename stem without paths or '..'")
    return f"{name}.raw.json"


def _validate_json(payload: bytes) -> None:
    if not payload.strip():
        raise CaptureError("stdin did not contain JSON")
    try:
        json.loads(payload)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise CaptureError("stdin did not contain valid JSON") from exc


def _open_scratch() -> int:
    try:
        SCRATCH_DIR.mkdir(mode=_DIRECTORY_MODE)
    except FileExistsError:
        pass
    except OSError as exc:
        raise CaptureError("scratch directory could not be created safely") from exc

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(SCRATCH_DIR, flags)
    except OSError as exc:
        raise CaptureError("scratch must be a real directory, not a symlink") from exc
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise CaptureError("scratch must be a real directory, not a symlink")
    try:
        os.fchmod(descriptor, _DIRECTORY_MODE)
    except OSError as exc:
        os.close(descriptor)
        raise CaptureError("scratch permissions could not be secured") from exc
    return descriptor


def write_capture(name: str, payload: bytes) -> Path:
    """Validate and exclusively create ``scratch/NAME.raw.json`` with mode 0600."""
    filename = _filename(name)
    _validate_json(payload)
    destination = SCRATCH_DIR / filename
    try:
        destination.relative_to(SCRATCH_DIR)
    except ValueError as exc:
        raise CaptureError("capture destination escaped scratch") from exc
    if SCRATCH_DIR.resolve(strict=False) == FIXTURES_DIR.resolve(strict=False):
        raise CaptureError("scratch must not be the committed fixture directory")

    directory_descriptor = _open_scratch()
    file_descriptor = -1
    created = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            file_descriptor = os.open(filename, flags, _FILE_MODE, dir_fd=directory_descriptor)
        except FileExistsError as exc:
            raise CaptureError("capture already exists; refusing to overwrite it") from exc
        except OSError as exc:
            raise CaptureError("capture could not be created safely") from exc
        created = True
        os.fchmod(file_descriptor, _FILE_MODE)
        with os.fdopen(file_descriptor, "wb") as stream:
            file_descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception as write_error:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        if created:
            try:
                os.unlink(filename, dir_fd=directory_descriptor)
            except OSError as cleanup_error:
                error = CaptureError(
                    f"capture write cleanup failed; residual capture remains at scratch/{filename}"
                )
                error.add_note(f"primary capture failure: {type(write_error).__name__}")
                raise error from cleanup_error
        raise
    finally:
        os.close(directory_descriptor)
    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read one JSON response from stdin into private scratch storage."
    )
    parser.add_argument("name", help="safe output stem; writes scratch/NAME.raw.json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(WARNING, file=sys.stderr)
    try:
        destination = write_capture(args.name, sys.stdin.buffer.read())
    except CaptureError as exc:
        print(f"record_fixture: {exc}", file=sys.stderr)
        return 2
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
