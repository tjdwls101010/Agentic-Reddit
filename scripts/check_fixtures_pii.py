#!/usr/bin/env python3
"""Reject structural signs of real data in committed synthetic JSON fixtures.

Usage: check_fixtures_pii.py

The scanner is stdlib-only and intentionally reports categories rather than
suspect values. It is a seatbelt for hand-authored fixtures, not a substitute
for human review of free text.
"""

from __future__ import annotations

import json
import math
import os
import re
import stat
import sys
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
CATEGORY_ORDER = (
    "unsafe-file",
    "invalid-json",
    "credential-key",
    "email",
    "phone",
    "high-entropy-secret",
    "non-synthetic-username",
)

_CREDENTIAL_WORDS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "bearer",
        "client_secret",
        "cookie",
        "cookies",
        "csrf",
        "password",
        "private_key",
        "secret",
        "session",
        "token",
    }
)
_USERNAME_KEYS = frozenset({"author", "author_name", "username", "user_name", "account_name"})
_PROFILE_URL_KEYS = frozenset({"author_url", "profile_url", "user_url"})
_SYNTHETIC_MARKERS = frozenset(
    {"dummy", "example", "fake", "fixture", "sample", "synthetic", "test"}
)
_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]+@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}"
    r"(?![A-Za-z0-9.\-])"
)
_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+\d{1,3}[ .-])?(?:\(\d{2,4}\)|\d{2,4})[ .-]\d{3,4}[ .-]\d{3,4}(?!\w)"
)
_TOKEN_RE = re.compile(r"[A-Za-z0-9+/_=\-]{32,}")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}(?:\.[A-Za-z0-9_\-]{8,})?\b")


def _key_words(key: str) -> tuple[str, ...]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return tuple(part for part in re.split(r"[^a-z0-9]+", separated.lower()) if part)


def _normalized_key(key: str) -> str:
    return "_".join(_key_words(key))


def _credential_shaped_key(key: str) -> bool:
    normalized = _normalized_key(key)
    if normalized in _CREDENTIAL_WORDS:
        return True
    words = _key_words(key)
    return bool(words and words[-1] in {"token", "secret", "password", "cookie"})


def _has_synthetic_marker(value: str) -> bool:
    words = set(re.split(r"[^a-z0-9]+", value.lower()))
    return bool(words & _SYNTHETIC_MARKERS)


def _profile_username(value: str) -> str | None:
    """Return a username from a Reddit profile URL or path."""
    parsed = urlparse(value)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc and parsed.hostname not in {
        "reddit.com",
        "www.reddit.com",
        "old.reddit.com",
        "np.reddit.com",
        "sh.reddit.com",
    }:
        return None
    parts = tuple(part for part in parsed.path.split("/") if part)
    if len(parts) == 2 and parts[0].casefold() in {"u", "user"}:
        return parts[1]
    return None


def _is_non_synthetic_username(value: object) -> bool:
    return (
        isinstance(value, str)
        and value not in {"[deleted]", "[removed]"}
        and not _has_synthetic_marker(value)
    )


def _is_normalized_user(value: Mapping[object, object]) -> bool:
    fullname = value.get("fullname")
    return isinstance(fullname, str) and fullname.startswith("t2_")


def _scan(
    value: object,
    categories: set[str],
    key: str = "",
    *,
    user_context: bool = False,
) -> None:
    if isinstance(value, Mapping):
        kind = value.get("kind")
        is_t2_thing = kind == "t2"
        is_user_record = user_context or _is_normalized_user(value)
        for child_key, child_value in value.items():
            key_text = str(child_key)
            normalized_key = _normalized_key(key_text)
            if _credential_shaped_key(key_text):
                categories.add("credential-key")
            if normalized_key in _USERNAME_KEYS and _is_non_synthetic_username(child_value):
                categories.add("non-synthetic-username")
            if (
                normalized_key == "author_fullname"
                and _is_non_synthetic_username(child_value)
                and not _has_synthetic_marker(str(value.get("author", "")))
            ):
                categories.add("non-synthetic-username")
            if (
                is_user_record
                and normalized_key == "name"
                and _is_non_synthetic_username(child_value)
            ):
                categories.add("non-synthetic-username")
            if normalized_key in _PROFILE_URL_KEYS and isinstance(child_value, str):
                username = _profile_username(child_value)
                if _is_non_synthetic_username(username):
                    categories.add("non-synthetic-username")
            if is_user_record and normalized_key == "url" and isinstance(child_value, str):
                username = _profile_username(child_value)
                if _is_non_synthetic_username(username):
                    categories.add("non-synthetic-username")
            _scan(
                child_value,
                categories,
                key_text,
                user_context=is_user_record or (is_t2_thing and key_text == "data"),
            )
        return
    if isinstance(value, list):
        for item in value:
            _scan(item, categories, key, user_context=user_context)
        return
    if not isinstance(value, str):
        return
    if _EMAIL_RE.search(value):
        categories.add("email")
    if _PHONE_RE.search(value):
        categories.add("phone")
    if _looks_like_secret(value):
        categories.add("high-entropy-secret")


def shannon_entropy(value: str) -> float:
    """Return Shannon entropy in bits per character."""
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for character in value:
        counts[character] = counts.get(character, 0) + 1
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _looks_like_secret(value: str) -> bool:
    if _JWT_RE.search(value):
        return True
    for match in _TOKEN_RE.finditer(value):
        candidate = match.group(0)
        if _has_synthetic_marker(candidate):
            continue
        classes = sum(
            (
                any(character.islower() for character in candidate),
                any(character.isupper() for character in candidate),
                any(character.isdigit() for character in candidate),
                any(character in "+/=_-" for character in candidate),
            )
        )
        if classes >= 3 and shannon_entropy(candidate) >= 4.0:
            return True
    return False


def _diagnostics(path: Path, categories: set[str]) -> list[str]:
    return [f"{path.name}: {category}" for category in CATEGORY_ORDER if category in categories]


def scan_file(path: Path) -> list[str]:
    """Return value-free diagnostics for one regular JSON fixture."""
    path = Path(path)
    try:
        status = path.lstat()
        if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
            return _diagnostics(path, {"unsafe-file"})
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, UnicodeError):
        return _diagnostics(path, {"unsafe-file"})
    except (json.JSONDecodeError, RecursionError):
        return _diagnostics(path, {"invalid-json"})

    categories: set[str] = set()
    _scan(payload, categories)
    return _diagnostics(path, categories)


def fixture_paths(directory: Path | None = None) -> tuple[Path, ...]:
    """Return direct JSON fixture files in deterministic order."""
    root = FIXTURES_DIR if directory is None else Path(directory)
    return tuple(sorted(root.glob("*.json"), key=lambda path: path.name)) if root.is_dir() else ()


def scan_fixtures(directory: Path | None = None) -> list[str]:
    """Scan the committed fixture scope, or an explicit directory in tests."""
    return [finding for path in fixture_paths(directory) for finding in scan_file(path)]


def main() -> int:
    paths = fixture_paths()
    findings = scan_fixtures()
    if findings:
        print("Fixture PII/secret scan FAILED:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(
            "Fixtures must be hand-authored synthetic JSON; inspect the named category.",
            file=sys.stderr,
        )
        return 1
    print(
        f"Fixture PII/secret scan OK ({len(paths)} file(s) checked); "
        "free text requires human review."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
