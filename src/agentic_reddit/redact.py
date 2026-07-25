"""Non-mutating redaction for diagnostic values.

Diagnostics may contain browser credentials and local profile locations. Normalized
output records deliberately bypass this module; optional raw attachments use it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

_REDACTED = "[REDACTED]"
_TEXT_TRUNCATE_LEN = 40
_DIAGNOSTIC_TEXT_MAX_LEN = 80
_CREDENTIAL_NAME_PATTERN = (
    r"(?:api[ _-]?key|access[_-]?token|token|secret|password|cookie|authorization|"
    r"proxy[_-]?authorization|session(?:[_-]?(?:id|token))?|csrf(?:[_-]?token)?)"
)
_CREDENTIAL_VALUE_RE = re.compile(
    rf"(?i)(\bbearer\s+|{_CREDENTIAL_NAME_PATTERN}\s*[=:]\s*(?:bearer\s+)?|"
    rf"[?&]{_CREDENTIAL_NAME_PATTERN}=)[^\s,;&#]+"
)
_LOCAL_PATH_RE = re.compile(
    r"(?<![\w/])(?:~|/(?:Users|home|var|private|tmp|opt|Library))(?:/[^\s,;]*)?"
)
_WINDOWS_PATH_RE = re.compile(r"(?<!\w)[A-Za-z]:[\\/][^\s,;]*")
_UNC_PATH_RE = re.compile(r"(?<!\w)\\\\[^\\/\s]+[\\/][^\s,;]*")

_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "proxy_authorization",
        "cookie",
        "set_cookie",
        "bearer",
        "csrf",
        "csrf_token",
        "x_csrf_token",
        "password",
        "passwd",
        "session",
        "session_id",
        "sessionid",
        "credential",
        "credentials",
    }
)
_PATH_KEYS = frozenset(
    {
        "browser_path",
        "browsers_path",
        "browser_profile",
        "browser_profile_path",
        "browser_dir",
        "browsers_dir",
        "chrome_path",
        "executable",
        "executable_path",
        "profile_dir",
        "profile_dir_override",
        "profile_path",
        "user_data_dir",
    }
)
_TEXT_KEYS = frozenset({"selftext", "body"})


def _normalized_key(key: str) -> str:
    return key.casefold().replace("-", "_")


def _is_sensitive_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    normalized = _normalized_key(key)
    compact = normalized.replace("_", "")
    return normalized in _SENSITIVE_KEYS or compact.endswith(
        ("token", "secret", "password", "apikey")
    )


def _is_path_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    normalized = _normalized_key(key)
    return normalized in _PATH_KEYS or (
        ("browser" in normalized or "profile" in normalized)
        and normalized.endswith(("path", "dir", "directory", "root"))
    )


def redact_text(value: str, max_len: int = _TEXT_TRUNCATE_LEN) -> str:
    """Bound diagnostic free text while retaining a useful prefix."""
    if len(value) <= max_len:
        return value
    return f"{value[:max_len]}...[redacted {len(value) - max_len} more chars]"


def _substitute(value: object, path_values: Iterable[object]) -> str:
    text = str(value)
    text = _CREDENTIAL_VALUE_RE.sub(r"\1" + _REDACTED, text)
    text = _LOCAL_PATH_RE.sub(_REDACTED, text)
    text = _WINDOWS_PATH_RE.sub(_REDACTED, text)
    text = _UNC_PATH_RE.sub(_REDACTED, text)
    for path_value in sorted(
        {str(path) for path in path_values if path is not None and str(path)},
        key=len,
        reverse=True,
    ):
        text = text.replace(path_value, _REDACTED)
    return text


def scrub_diagnostic(value: object, *, path_values: Iterable[object] = ()) -> str:
    """Redact unstructured diagnostic text without exposing local values."""
    text = _substitute(value, path_values)
    if len(text) > _DIAGNOSTIC_TEXT_MAX_LEN:
        return f"[REDACTED diagnostic text: {len(text)} chars]"
    return text


def scrub_usage_error(message: str) -> str:
    """Redact an argparse usage error, which is argv rather than scraped content.

    The length bound in ``scrub_diagnostic`` exists to cap unbounded third-party
    text.  A usage error carries none, so bounding one by length only destroys
    the diagnostic: every ``invalid choice`` message exceeds the bound because it
    enumerates the whole subcommand surface.
    """
    return _substitute(message, ())


def redact(value: Any) -> Any:
    """Recursively scrub diagnostics without mutating caller-owned containers.

    Built-in container types retain their type.  Unknown scalar types are
    returned unchanged because they do not have a safe generic copying contract.
    """
    return _redact(value, active=set())


def _redact(value: Any, *, active: set[int]) -> Any:
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            return _REDACTED
        active.add(identity)
        try:
            return {
                key: (
                    _REDACTED
                    if _is_sensitive_key(key) or _is_path_key(key)
                    else redact_text(item)
                    if (
                        isinstance(key, str)
                        and isinstance(item, str)
                        and _normalized_key(key) in _TEXT_KEYS
                    )
                    else _redact(item, active=active)
                )
                for key, item in value.items()
            }
        finally:
            active.remove(identity)
    if isinstance(value, list):
        identity = id(value)
        if identity in active:
            return _REDACTED
        active.add(identity)
        try:
            return [_redact(item, active=active) for item in value]
        finally:
            active.remove(identity)
    if isinstance(value, tuple):
        return tuple(_redact(item, active=active) for item in value)
    if isinstance(value, set):
        return {_redact(item, active=active) for item in value}
    if isinstance(value, frozenset):
        return frozenset(_redact(item, active=active) for item in value)
    return value
