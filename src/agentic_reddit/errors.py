"""Typed failures and their command-line exit semantics."""

from __future__ import annotations

EXIT_CODES = {
    0: "success",
    1: "usage error, invalid identifier, setup failure, or unexpected failure",
    2: "browser or profile is not ready; run agentic-reddit setup",
    3: "rate-limited",
    4: "Reddit response shape drift or challenge page where JSON was expected",
    5: "target does not exist or is unavailable",
    7: "since boundary was not confirmed before the run stopped",
}


class AgenticRedditError(Exception):
    """Base class for every expected Agentic Reddit failure."""

    exit_code = 1


class BrowserNotReadyError(AgenticRedditError):
    """The isolated browser or selected profile is not ready for reads."""

    exit_code = 2


class SetupRequiredError(BrowserNotReadyError):
    """The selected profile must be warmed with ``agentic-reddit setup``."""


class ChallengeError(AgenticRedditError):
    """Reddit returned a challenge page where JSON was expected."""

    exit_code = 4


class RateLimitedError(AgenticRedditError):
    """Reddit's request budget is exhausted, optionally until ``reset_at``."""

    exit_code = 3

    def __init__(
        self,
        reset_at: float | None = None,
        message: str = "Reddit rate limit reached",
    ) -> None:
        super().__init__(message)
        self.reset_at = reset_at


class EnvelopeParseError(AgenticRedditError):
    """A Reddit JSON response no longer matches its expected envelope shape."""

    exit_code = 4


class NotFoundError(AgenticRedditError):
    """The requested Reddit target does not exist."""

    exit_code = 5


class TargetUnavailableError(NotFoundError):
    """The target is private, banned, quarantined, suspended, or deleted."""


class InvalidIdentifierError(AgenticRedditError, ValueError):
    """A Reddit identifier or profile name failed validation."""


class BrowserSetupError(AgenticRedditError):
    """The isolated browser could not be installed or provisioned."""
