"""Runtime defaults, storage paths, and the non-bypassable request-rate guardrail."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from .errors import InvalidIdentifierError

APP_NAME = "agentic-reddit"
DEFAULT_PROFILE_NAME = "default"
ENV_PREFIX = "AGENTIC_REDDIT_"
ENV_PROFILE_DIR = f"{ENV_PREFIX}PROFILE_DIR"
_MAX_PROFILE_NAME_LENGTH = 64
_PROFILE_NAME_RE = re.compile(rf"[A-Za-z0-9._-]{{1,{_MAX_PROFILE_NAME_LENGTH}}}\Z", re.ASCII)

MIN_REQUEST_PAUSE_SECONDS = 1.0
DEFAULT_REQUEST_PAUSE = MIN_REQUEST_PAUSE_SECONDS
DEFAULT_MAX_REQUESTS = 100
REDDIT_BASE = "https://www.reddit.com"


def _user_data_dir() -> Path:
    from platformdirs import user_data_dir

    return Path(user_data_dir(APP_NAME))


def _validate_profile_name(profile: str) -> str:
    """Return a safe profile basename or raise a package-owned validation error."""
    if (
        not isinstance(profile, str)
        or profile in {".", ".."}
        or _PROFILE_NAME_RE.fullmatch(profile) is None
    ):
        raise InvalidIdentifierError("invalid profile name")
    return profile


def profile_dir(
    profile: str = DEFAULT_PROFILE_NAME,
    *,
    profile_dir_override: str | Path | None = None,
) -> Path:
    """Resolve a validated profile directory without creating it."""
    profile_name = _validate_profile_name(profile)
    if profile_dir_override is not None:
        profiles_root = Path(profile_dir_override)
    elif env_override := os.environ.get(ENV_PROFILE_DIR):
        profiles_root = Path(env_override)
    else:
        profiles_root = _user_data_dir() / "profiles"
    return profiles_root / profile_name


def browser_profile_dir(
    profile: str = DEFAULT_PROFILE_NAME,
    *,
    profile_dir_override: str | Path | None = None,
) -> Path:
    """Resolve the persistent browser context for a validated profile."""
    return profile_dir(profile, profile_dir_override=profile_dir_override) / "browser"


def browsers_dir() -> Path:
    """Resolve the isolated browser-install directory without creating it."""
    return _user_data_dir() / "browsers"


def default_output_dir() -> Path:
    """Resolve the default output directory outside the working tree."""
    return _user_data_dir() / "output"


def clamp_request_pause(min_s: float) -> float:
    """Enforce the mandatory minimum inter-request delay."""
    if min_s >= MIN_REQUEST_PAUSE_SECONDS:
        return min_s
    print(
        f"agentic-reddit: request pause {min_s}s raised to "
        f"{MIN_REQUEST_PAUSE_SECONDS}s (non-bypassable minimum)",
        file=sys.stderr,
    )
    return MIN_REQUEST_PAUSE_SECONDS
