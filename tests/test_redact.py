from __future__ import annotations

from pathlib import Path

from agentic_reddit.redact import redact, redact_text, scrub_diagnostic, scrub_usage_error


def test_redact_scrubs_nested_credential_keys_and_headers() -> None:
    diagnostic = {
        "headers": {
            "Authorization": "Bearer live-token",
            "X-CSRF-Token": "csrf-value",
            "Accept": "application/json",
        },
        "response": [{"cookie": "session=value", "access_token": "nested-token"}],
    }

    result = redact(diagnostic)

    assert result == {
        "headers": {
            "Authorization": "[REDACTED]",
            "X-CSRF-Token": "[REDACTED]",
            "Accept": "application/json",
        },
        "response": [{"cookie": "[REDACTED]", "access_token": "[REDACTED]"}],
    }
    assert diagnostic["headers"]["Authorization"] == "Bearer live-token"
    assert diagnostic["response"][0]["access_token"] == "nested-token"


def test_redact_scrubs_browser_and_profile_paths_without_hiding_other_values() -> None:
    profile_path = Path("/private/tmp/agentic-reddit/default")
    browser_path = "/Users/example/Library/Caches/browser/chrome"
    diagnostic = {
        "profile_dir": profile_path,
        "nested": {"browser-path": browser_path},
        "request_count": 3,
        "status": "ready",
    }

    result = redact(diagnostic)

    assert result == {
        "profile_dir": "[REDACTED]",
        "nested": {"browser-path": "[REDACTED]"},
        "request_count": 3,
        "status": "ready",
    }
    assert diagnostic["profile_dir"] == profile_path
    assert diagnostic["nested"]["browser-path"] == browser_path


def test_redact_truncates_free_text_and_preserves_mixed_container_types() -> None:
    selftext = "s" * 45
    body = "b" * 44
    diagnostic = {
        "selftext": selftext,
        "items": (None, True, {"body": body}),
        "tags": frozenset({"ordinary"}),
    }

    result = redact(diagnostic)

    assert result["selftext"] == redact_text(selftext)
    assert result["items"] == (None, True, {"body": redact_text(body)})
    assert isinstance(result["items"], tuple)
    assert result["tags"] == frozenset({"ordinary"})
    assert diagnostic["selftext"] == selftext
    assert diagnostic["items"][2]["body"] == body


def test_scrub_diagnostic_redacts_credentials_and_platform_paths() -> None:
    token = "live-token"
    posix_path = "/private/tmp/agentic-reddit/profile"
    windows_path = r"C:\Users\example\AppData\Local\profile"
    unc_path = r"\\server\share\profile"
    messages = (
        (scrub_diagnostic(f"token={token}"), token),
        (scrub_diagnostic(f"https://example.test/?token={token}"), token),
        (scrub_diagnostic(f"cache {posix_path}"), posix_path),
        (scrub_diagnostic(f"profile {windows_path}"), windows_path),
        (scrub_diagnostic(f"output {unc_path}"), unc_path),
    )

    for message, value in messages:
        assert value not in message
        assert "[REDACTED]" in message


def test_scrub_diagnostic_redacts_custom_paths_and_bounds_free_text() -> None:
    custom_profile = "/srv/isolated-profile"
    custom_output = "/mnt/private-output/result.json"
    message = scrub_diagnostic(
        f"failed profile={custom_profile} output={custom_output}",
        path_values=(custom_profile, custom_output),
    )
    bounded = scrub_diagnostic("untrusted diagnostic value " * 10)

    assert custom_profile not in message
    assert custom_output not in message
    assert len(bounded) <= 80
    assert "untrusted diagnostic value" not in bounded


def test_scrub_usage_error_keeps_long_messages_and_still_scrubs_secrets() -> None:
    choices = ", ".join(
        f"'{name}'" for name in ("setup", "status", "doctor", "catalog", "schema", "subreddit-info")
    )
    usage_error = f"argument command: invalid choice: 'nosuchcmd' (choose from {choices})"
    scrubbed = scrub_usage_error(f"{usage_error} token=live-token /Users/example/profile")

    assert len(usage_error) > 80
    assert usage_error in scrubbed
    assert "live-token" not in scrubbed
    assert "/Users/example/profile" not in scrubbed
