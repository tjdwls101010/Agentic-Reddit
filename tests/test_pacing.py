"""Tests for the non-bypassable Reddit pacing governor."""

from __future__ import annotations

import pytest

from agentic_reddit.errors import RateLimitedError
from agentic_reddit.pacing import PacingGovernor


def _headers(remaining: str = "90", reset: str = "60", used: str = "10") -> dict[str, str]:
    return {
        "x-ratelimit-remaining": remaining,
        "x-ratelimit-reset": reset,
        "x-ratelimit-used": used,
    }


def test_floor_is_clamped_before_every_request() -> None:
    sleeps: list[float] = []
    governor = PacingGovernor(request_pause=0, sleeper=sleeps.append)

    governor.before_request()
    governor.before_request()

    assert sleeps == [1.0, 1.0]


def test_delay_stretches_when_the_budget_is_depleted() -> None:
    sleeps: list[float] = []
    governor = PacingGovernor(sleeper=sleeps.append)
    governor.observe_response(_headers(remaining="5", reset="60", used="95"))

    governor.before_request()

    assert sleeps == [12.0]


def test_zero_remaining_raises_with_the_reset_timestamp() -> None:
    governor = PacingGovernor(clock=lambda: 100.0)

    with pytest.raises(RateLimitedError) as raised:
        governor.observe_response(_headers(remaining="0", reset="12", used="100"))

    assert raised.value.reset_at == 112.0


def test_wait_on_limit_only_waits_within_the_bound() -> None:
    sleeps: list[float] = []
    waiting = PacingGovernor(
        wait_on_limit=True,
        max_wait=10,
        clock=lambda: 100.0,
        sleeper=sleeps.append,
    )

    waiting.observe_response(_headers(remaining="0", reset="10", used="100"))
    waiting.before_request()

    assert sleeps == [10.0, 1.0]

    bounded = PacingGovernor(wait_on_limit=True, max_wait=9, clock=lambda: 100.0)
    with pytest.raises(RateLimitedError) as raised:
        bounded.observe_response(_headers(remaining="0", reset="10", used="100"))

    assert raised.value.reset_at == 110.0


@pytest.mark.parametrize(
    "headers",
    [None, {}, {"x-ratelimit-remaining": "not-a-number"}],
)
def test_missing_or_malformed_headers_fall_back_to_the_floor(
    headers: dict[str, str] | None,
) -> None:
    sleeps: list[float] = []
    governor = PacingGovernor(sleeper=sleeps.append)

    governor.observe_response(headers)
    governor.before_request()

    assert sleeps == [1.0]


def test_429_raises_without_waiting_or_retrying() -> None:
    sleeps: list[float] = []
    governor = PacingGovernor(
        wait_on_limit=True,
        max_wait=60,
        clock=lambda: 100.0,
        sleeper=sleeps.append,
    )

    with pytest.raises(RateLimitedError) as raised:
        governor.observe_response(_headers(remaining="0", reset="20", used="100"), 429)

    assert raised.value.reset_at == 120.0
    assert sleeps == []
