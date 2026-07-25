"""Offline CLI contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agentic_reddit import cli, errors

_READ_COMMANDS = {
    "subreddit": ["python"],
    "post": ["abc123"],
    "user": ["spez"],
    "search": ["synthetic query"],
    "subreddits": ["synthetic query"],
    "subreddit-info": ["python"],
}
_OPERATIONAL_DEFAULTS = {
    "format": "json",
    "output": None,
    "wait_on_limit": False,
    "max_wait": None,
    "raw": False,
    "no_redact": False,
    "verbose": False,
}


def test_read_parser_capabilities_and_defaults() -> None:
    parser = cli.build_parser()

    for command, positionals in _READ_COMMANDS.items():
        args = parser.parse_args([command, *positionals])
        assert {
            name: getattr(args, name) for name in _OPERATIONAL_DEFAULTS
        } == _OPERATIONAL_DEFAULTS
        assert hasattr(args, "profile")
        assert args.profile_dir is None

    for command in ("subreddit", "user", "search"):
        args = parser.parse_args([command, *_READ_COMMANDS[command]])
        assert (args.limit, args.since, args.until) == (None, None, None)
    assert parser.parse_args(["subreddits", "query"]).limit is None
    assert not hasattr(parser.parse_args(["subreddits", "query"]), "since")
    assert not hasattr(parser.parse_args(["subreddit-info", "python"]), "limit")
    assert not hasattr(parser.parse_args(["post", "abc123"]), "limit")

    subreddit = parser.parse_args(["subreddit", "python"])
    assert (subreddit.sort, subreddit.time) == ("hot", "day")
    post = parser.parse_args(["post", "abc123"])
    assert (post.comment_sort, post.depth, post.comment_limit) == ("confidence", None, 500)
    user = parser.parse_args(["user", "spez"])
    assert (user.type, user.sort, user.time) == ("overview", None, None)
    search = parser.parse_args(["search", "query"])
    assert (search.type, search.sort, search.time, search.subreddit) == ("link", None, None, None)
    assert tuple(
        parser.parse_args(["subreddit", "python", "--sort", choice]).sort
        for choice in ["hot", "new", "top", "rising", "controversial"]
    ) == ("hot", "new", "top", "rising", "controversial")
    assert tuple(
        parser.parse_args(["post", "abc123", "--comment-sort", choice]).comment_sort
        for choice in ["confidence", "top", "best", "new", "controversial", "old", "qa"]
    ) == ("confidence", "top", "best", "new", "controversial", "old", "qa")

    common = parser.parse_args(
        [
            "subreddit",
            "python",
            "--format",
            "ndjson",
            "--output",
            "result.ndjson",
            "--limit",
            "2",
            "--since",
            "2025-01-02",
            "--until",
            "2025-01-03",
            "--wait-on-limit",
            "--max-wait",
            "3.5",
            "--profile",
            "test",
            "--profile-dir",
            "profiles",
            "--raw",
            "-v",
        ]
    )
    assert common.limit == 2
    assert str(common.since) == "2025-01-02"
    assert str(common.until) == "2025-01-03"
    assert common.wait_on_limit and common.max_wait == 3.5
    assert (common.profile, common.profile_dir, common.raw, common.verbose) == (
        "test",
        "profiles",
        True,
        True,
    )


def test_catalog_and_schema_commands_emit_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["catalog"]) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert catalog == cli.build_catalog()

    assert cli.main(["schema"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert {"Post", "Comment", "Subreddit", "User", "Media"} <= set(schema["$defs"])


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["subreddit"],
        ["subreddit", "python", "--format", "yaml"],
        ["subreddit", "python", "--limit", "-1"],
        ["subreddit", "python", "--no-redact"],
        ["post", "abc123", "--limit", "1"],
        ["post", "abc123", "--since", "2025-01-02"],
        ["subreddits", "query", "--since", "2025-01-02"],
        ["subreddit-info", "python", "--limit", "1"],
        ["search", "query", "--type", "sr", "--since", "2025-01-02"],
    ],
)
def test_parser_errors_exit_one(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(argv)

    assert raised.value.code == 1


@pytest.mark.parametrize(
    "credential",
    [
        "api_key=api-secret",
        "authorization=Bearer authorization-secret",
        "session=session-secret",
        "token=token-secret",
    ],
)
def test_parser_error_redacts_rejected_credential_values(
    credential: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(["subreddit", "python", "--limit", credential])

    assert raised.value.code == 1
    diagnostic = capsys.readouterr().err
    assert credential.split("=", 1)[1] not in diagnostic
    assert "[REDACTED]" in diagnostic


def test_verbose_exception_redacts_configured_paths_without_overmatching(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    profile_dir = "/srv/agentic/profile-data"
    output = "output/run.json"
    unrelated = "/srv/agentic/other-data output/run-other.json"

    def fail(_: Any) -> int:
        raise RuntimeError(f"failed {profile_dir} {output} {unrelated}")

    monkeypatch.setitem(cli._HANDLERS, "subreddit", fail)

    assert (
        cli.main(
            [
                "subreddit",
                "python",
                "--profile-dir",
                profile_dir,
                "--output",
                output,
                "--verbose",
            ]
        )
        == 1
    )

    diagnostic = capsys.readouterr().err
    assert profile_dir not in diagnostic
    assert output not in diagnostic
    assert unrelated in diagnostic


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (errors.BrowserNotReadyError(), 2),
        (errors.RateLimitedError(), 3),
        (errors.ChallengeError(), 4),
        (errors.NotFoundError(), 5),
        (errors.AgenticRedditError(), 1),
        (RuntimeError("unexpected"), 1),
    ],
)
def test_canonical_exit_codes(
    monkeypatch: pytest.MonkeyPatch, failure: Exception, expected: int
) -> None:
    def fail(_: Any) -> int:
        raise failure

    monkeypatch.setitem(cli._HANDLERS, "catalog", fail)
    assert cli.main(["catalog"]) == expected


def test_exit_code_table_matches_the_documented_contract() -> None:
    assert errors.EXIT_CODES == {
        0: "success",
        1: "usage error, invalid identifier, setup failure, or unexpected failure",
        2: "browser or profile is not ready; run agentic-reddit setup",
        3: "rate-limited",
        4: "Reddit response shape drift or challenge page where JSON was expected",
        5: "target does not exist or is unavailable",
        7: "since boundary was not confirmed before the run stopped",
    }


@pytest.mark.parametrize(
    ("command", "fmt", "label"),
    [
        ("subreddit", "json", "posts"),
        ("post", "ndjson", "posts"),
        ("user", "json", "posts"),
        ("search", "ndjson", "posts"),
        ("subreddits", "json", "subreddits"),
        ("subreddit-info", "ndjson", "subreddits"),
    ],
)
def test_mocked_read_handlers_write_atomically_and_summarize_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command: str,
    fmt: str,
    label: str,
) -> None:
    import agentic_reddit.retrieve as retrieve

    result = SimpleNamespace(
        items=[{"id": "synthetic"}], requests_made=2, stop_reason="listing_exhausted"
    )
    function_name = {
        "subreddit": "fetch_subreddit",
        "post": "fetch_post",
        "user": "fetch_user",
        "search": "search",
        "subreddits": "find_subreddits",
        "subreddit-info": "fetch_subreddit_info",
    }[command]
    monkeypatch.setattr(retrieve, function_name, lambda *_args, **_kwargs: result)
    monkeypatch.setattr(cli, "_with_browser", lambda args, operation: operation(object()))
    original_replace = Path.replace
    replacements: list[tuple[Path, Path]] = []

    def record_replace(source: Path, destination: Path) -> Path:
        replacements.append((source, destination))
        return original_replace(source, destination)

    monkeypatch.setattr(Path, "replace", record_replace)
    output = tmp_path / f"result.{fmt}"
    assert (
        cli.main([command, *_READ_COMMANDS[command], "--format", fmt, "--output", str(output)]) == 0
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("\n") == 1
    assert f"1 {label}, range none..none, stop reason: listing_exhausted, budget " in captured.err
    assert captured.err.rstrip().endswith(f"Saved to {output}")
    assert len(replacements) == 1
    assert replacements[0][1] == output
    assert replacements[0][0].parent == output.parent
    assert replacements[0][0].name.startswith(".ar-")
    assert not replacements[0][0].exists()
    if fmt == "json":
        assert json.loads(output.read_text(encoding="utf-8")) == [{"id": "synthetic"}]
    else:
        assert [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()] == [
            {"id": "synthetic"}
        ]


def test_no_redact_warns_before_mocked_raw_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import agentic_reddit.retrieve as retrieve

    result = SimpleNamespace(
        items=[{"id": "synthetic", "raw": {"token": "unsafe"}}],
        requests_made=1,
        stop_reason="listing_exhausted",
    )
    monkeypatch.setattr(retrieve, "fetch_subreddit", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(cli, "_with_browser", lambda args, operation: operation(object()))
    output = tmp_path / "raw.json"

    assert cli.main(["subreddit", "python", "--raw", "--no-redact", "--output", str(output)]) == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines()[0] == "warning: --no-redact may write sensitive raw data"
    assert len(captured.err.splitlines()) == 2
    assert json.loads(output.read_text(encoding="utf-8"))[0]["raw"]["token"] == "unsafe"


def test_with_browser_configures_governor_and_preserves_observed_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agentic_reddit.session as session

    browsers: list[Any] = []

    class FakeBrowserSession:
        def __init__(self, *_args: Any, **kwargs: Any) -> None:
            self.pacing = kwargs["pacing"]
            browsers.append(self)

        def __enter__(self) -> FakeBrowserSession:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

    monkeypatch.setattr(session, "BrowserSession", FakeBrowserSession)
    args = cli.build_parser().parse_args(
        ["subreddit", "python", "--wait-on-limit", "--max-wait", "12.5"]
    )
    result = SimpleNamespace()

    def operation(browser: FakeBrowserSession) -> SimpleNamespace:
        browser.pacing.remaining = 88.0
        browser.pacing.used = 12.0
        browser.pacing.reset = 42.0
        return result

    assert cli._with_browser(args, operation) is result
    assert browsers[0].pacing.wait_on_limit is True
    assert browsers[0].pacing.max_wait == 12.5
    assert result.remaining == 88.0
    assert result.used == 12.0
    assert result.reset == 42.0


@pytest.mark.parametrize(
    ("remaining", "reset", "used", "expected_budget"),
    [
        (88.0, 42.0, 12.0, "88.0/12.0"),
        (88.0, None, 12.0, "unknown/unknown"),
        (None, None, None, "unknown/unknown"),
    ],
)
def test_finish_reports_observed_or_unknown_budget(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    remaining: float | None,
    reset: float | None,
    used: float | None,
    expected_budget: str,
) -> None:
    output = tmp_path / "result.json"
    args = cli.build_parser().parse_args(["subreddit", "python", "--output", str(output)])
    result = SimpleNamespace(
        items=[],
        requests_made=999,
        stop_reason="listing_exhausted",
        remaining=remaining,
        used=used,
        reset=reset,
    )

    assert cli._finish(result, "python", args) == 0

    assert f"budget {expected_budget}. Saved to {output}" in capsys.readouterr().err


def test_raw_output_uses_shared_redactor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    raw = {"token": "unsafe"}
    calls: list[object] = []

    def fake_redact(value: object) -> object:
        calls.append(value)
        return {"redacted": True}

    monkeypatch.setattr(cli.redact, "redact", fake_redact)
    output = tmp_path / "raw.json"

    cli._write_rows([{"id": "synthetic", "raw": raw}], output, "json", redact_raw=True)

    assert calls == [raw]
    assert json.loads(output.read_text(encoding="utf-8")) == [
        {"id": "synthetic", "raw": {"redacted": True}}
    ]


def test_finish_uses_real_model_type_counts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = cli.build_parser().parse_args(
        ["post", "abc123", "--output", str(tmp_path / "result.json")]
    )
    monkeypatch.setattr(cli, "_write_rows", lambda *_args, **_kwargs: None)
    result = SimpleNamespace(
        items=[
            object.__new__(cli.model.Post),
            object.__new__(cli.model.Comment),
            object.__new__(cli.model.Comment),
        ],
        stop_reason="tree_complete",
        remaining=88.0,
        reset=42.0,
        used=12.0,
    )

    assert cli._finish(result, "abc123", args) == 0
    assert (
        "1 post, 2 comments, range none..none, stop reason: tree_complete, budget 88.0/12.0."
        in capsys.readouterr().err
    )


def test_finish_returns_rate_and_since_exit_codes_after_writing(tmp_path: Path) -> None:
    output = tmp_path / "partial.json"
    args = cli.build_parser().parse_args(
        ["subreddit", "python", "--since", "2025-01-02", "--output", str(output)]
    )
    result = SimpleNamespace(
        items=[{"id": "partial"}],
        stop_reason="rate_limited",
        remaining=0.0,
        used=100.0,
        since_target_crossed=False,
    )

    assert cli._finish(result, "python", args) == 7
    assert json.loads(output.read_text(encoding="utf-8")) == [{"id": "partial"}]

    args = cli.build_parser().parse_args(["subreddit", "python", "--output", str(output)])
    assert cli._finish(result, "python", args) == 3


def test_raw_redaction_covers_nested_reply_attachments(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(
        cli.redact, "redact", lambda value: calls.append(value) or {"redacted": True}
    )
    output = tmp_path / "raw.json"
    rows = [{"raw": {"token": "top"}, "replies": [{"raw": {"token": "reply"}}]}]

    cli._write_rows(rows, output, "json", redact_raw=True)

    assert calls == [{"token": "top"}, {"token": "reply"}]
    assert json.loads(output.read_text(encoding="utf-8")) == [
        {"raw": {"redacted": True}, "replies": [{"raw": {"redacted": True}}]}
    ]


def test_finish_escapes_control_characters_in_display_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "result\nname.json"
    args = cli.build_parser().parse_args(["subreddit", "python", "--output", str(output)])
    result = SimpleNamespace(items=[], stop_reason="listing_exhausted", remaining=None, used=None)

    assert cli._finish(result, "python", args) == 0
    assert output.exists()
    assert "Saved to " + str(output).replace("\n", "\\x0a") in capsys.readouterr().err

def test_finish_escapes_supplementary_format_character_in_display_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    format_character = "\U000e0001"
    output = tmp_path / f"result{format_character}name.json"
    args = cli.build_parser().parse_args(["subreddit", "python", "--output", str(output)])
    result = SimpleNamespace(items=[], stop_reason="listing_exhausted", remaining=None, used=None)

    assert cli._finish(result, "python", args) == 0
    assert output.exists()
    summary = capsys.readouterr().err
    assert r"\U000e0001" in summary
    assert format_character not in summary


def test_exception_diagnostic_is_bounded_and_scrubbed() -> None:
    message = cli._scrub_diagnostic(
        RuntimeError("token=live-secret path=/Users/example/Library/Application Support/profile")
    )

    assert "live-secret" not in message
    assert "/Users/example" not in message
    assert len(message) <= 80


def test_atomic_writer_cleans_temporary_files_after_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "result.json"
    real_dump = json.dump
    monkeypatch.setattr(
        cli.json, "dump", lambda *_args, **_kwargs: (_ for _ in ()).throw(TypeError("bad row"))
    )

    with pytest.raises(TypeError, match="bad row"):
        cli._write_rows([{"id": "synthetic"}], output, "json")
    assert not list(tmp_path.glob(".ar-*"))

    monkeypatch.setattr(cli.json, "dump", real_dump)
    monkeypatch.setattr(
        Path,
        "replace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("replace failed")),
    )
    with pytest.raises(OSError, match="replace failed"):
        cli._write_rows([{"id": "synthetic"}], output, "json")
    assert not list(tmp_path.glob(".ar-*"))


def test_doctor_prints_structured_diagnostics(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from agentic_reddit import session

    diagnostics = {
        "browser_executable": True,
        "profile": True,
        "listing": True,
        "rate_budget": {"remaining": 99.0, "reset": 300.0, "used": 1.0},
    }
    monkeypatch.setattr(session, "run_doctor", lambda *_args, **_kwargs: diagnostics)

    assert cli.main(["doctor"]) == 0
    assert json.loads(capsys.readouterr().err) == diagnostics
