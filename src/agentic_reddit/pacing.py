"""Rate-limit-aware request pacing for Reddit JSON requests."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from typing import Any

from . import config
from .errors import RateLimitedError


class PacingGovernor:
    """Enforce the request floor and preserve Reddit's observed rate budget."""

    def __init__(
        self,
        request_pause: float | None = None,
        *,
        wait_on_limit: bool = False,
        max_wait: float | None = None,
        clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_wait is not None and max_wait < 0:
            raise ValueError("max_wait must be non-negative")

        requested_pause = (
            config.MIN_REQUEST_PAUSE_SECONDS if request_pause is None else request_pause
        )
        self.request_pause = config.clamp_request_pause(float(requested_pause))
        self.wait_on_limit = wait_on_limit
        self.max_wait = max_wait
        self._clock = clock
        self._sleeper = sleeper
        self.remaining: float | None = None
        self.reset: float | None = None
        self.used: float | None = None

    def before_request(self) -> None:
        """Sleep before every request, using the latest valid rate-limit headers."""
        self.request_pause = config.clamp_request_pause(float(self.request_pause))
        delay = self.request_pause
        if self._budget_is_depleted():
            raise RateLimitedError(reset_at=self._reset_at())
        if self._budget_is_depleted_enough_to_pace():
            assert self.reset is not None
            assert self.remaining is not None
            delay = max(delay, self.reset / self.remaining)
        self._sleeper(delay)

    def observe_response(
        self,
        headers: Mapping[str, Any] | None,
        status_code: int | None = None,
    ) -> None:
        """Record rate headers and stop or bounded-wait when the budget is exhausted."""
        parsed = _parse_rate_headers(headers)
        if parsed is None:
            self.remaining = None
            self.reset = None
            self.used = None
        else:
            self.remaining, self.reset, self.used = parsed

        if status_code == 429:
            raise RateLimitedError(reset_at=self._reset_at())
        if parsed is None:
            return
        if self.remaining != 0:
            return

        reset_at = self._reset_at()
        if self.wait_on_limit and self._can_wait_for_reset():
            self._sleeper(max(0.0, self.reset))
            self.remaining = None
            self.reset = None
            self.used = None
            return
        raise RateLimitedError(reset_at=reset_at)

    def _budget_is_depleted(self) -> bool:
        return self.remaining == 0 and self.reset is not None

    def _budget_is_depleted_enough_to_pace(self) -> bool:
        return (
            self.remaining is not None
            and self.remaining > 0
            and self.reset is not None
            and self.used is not None
            and self.remaining <= self.used
        )

    def _can_wait_for_reset(self) -> bool:
        return (
            self.reset is not None
            and self.reset >= 0
            and (self.max_wait is None or self.reset <= self.max_wait)
        )

    def _reset_at(self) -> float | None:
        if self.reset is None:
            return None
        return self._clock() + max(0.0, self.reset)


def _parse_rate_headers(
    headers: Mapping[str, Any] | None,
) -> tuple[float, float, float] | None:
    """Return a complete, non-negative rate-header set, or no budget data."""
    if headers is None:
        return None

    normalized = {str(key).lower(): value for key, value in headers.items()}
    try:
        remaining = float(normalized["x-ratelimit-remaining"])
        reset = float(normalized["x-ratelimit-reset"])
        used = float(normalized["x-ratelimit-used"])
    except (KeyError, TypeError, ValueError):
        return None

    if (
        not all(math.isfinite(value) for value in (remaining, reset, used))
        or remaining < 0
        or reset < 0
        or used < 0
    ):
        return None
    return remaining, reset, used
