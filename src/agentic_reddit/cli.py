"""Command-line interface for read-only Agentic Reddit primitives."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import tempfile
import unicodedata
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from . import __version__, config, errors, identity, model, redact

CATALOG_VERSION = 1
_TIME_CHOICES = ["hour", "day", "week", "month", "year", "all"]


class _ArgumentParser(argparse.ArgumentParser):
    """Reserve exit code 2 for a browser/profile that needs setup."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {redact.scrub_diagnostic(message)}\n")


def _parse_iso_date(value: str) -> date:
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}") from None


def _add_profile_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile", default=config.DEFAULT_PROFILE_NAME, help="Browser profile name."
    )
    parser.add_argument("--profile-dir", default=None, help="Override the profile directory.")


def _add_read_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format", choices=["json", "ndjson"], default="json", help="Output format."
    )
    parser.add_argument("--output", default=None, help="Destination file path.")
    parser.add_argument("--wait-on-limit", action="store_true", help="Wait for a rate-limit reset.")
    parser.add_argument(
        "--max-wait", type=float, default=None, help="Maximum rate-limit wait in seconds."
    )
    _add_profile_args(parser)
    parser.add_argument("--raw", action="store_true", help="Include source payloads in output.")
    parser.add_argument(
        "--no-redact", action="store_true", help="Do not redact included source payloads."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Include a scrubbed failure diagnostic."
    )


def _add_limit_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=int, default=None, help="Maximum items to write.")


def _add_date_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--since", type=_parse_iso_date, default=None, help="Earliest UTC date to include."
    )
    parser.add_argument(
        "--until", type=_parse_iso_date, default=None, help="Latest UTC date to include."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="agentic-reddit", description="Read-only Reddit retrieval. Commands write JSON files."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"agentic-reddit {__version__}",
        help="Show the package version.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    setup = commands.add_parser("setup", help="Provision the isolated browser and warm a profile.")
    setup.add_argument(
        "--force", action="store_true", help="Re-provision an existing browser or profile."
    )
    setup.add_argument(
        "--headed", action="store_true", help="Run the browser with a visible window."
    )
    _add_profile_args(setup)
    setup.add_argument(
        "--timeout-seconds", type=float, default=120.0, help="Setup timeout in seconds."
    )

    status = commands.add_parser("status", help="Classify browser and profile readiness.")
    _add_profile_args(status)
    status.add_argument("--json", action="store_true", help="Write readiness details as JSON.")

    doctor = commands.add_parser("doctor", help="Perform a bounded browser/profile diagnostic.")
    _add_profile_args(doctor)

    catalog = commands.add_parser(
        "catalog", help="Emit the parser-derived CLI catalog as JSON (offline)."
    )
    catalog.add_argument("--json", action="store_true", help="Request JSON output.")
    schema = commands.add_parser("schema", help="Emit the output JSON Schema (offline).")
    schema.add_argument("--json", action="store_true", help="Request JSON output.")

    subreddit = commands.add_parser("subreddit", help="Read a subreddit listing.")
    subreddit.add_argument("name", help="Subreddit name or URL.")
    subreddit.add_argument(
        "--sort",
        choices=["hot", "new", "top", "rising", "controversial"],
        default="hot",
        help="Listing sort order.",
    )
    subreddit.add_argument("--time", choices=_TIME_CHOICES, default="day", help="Sort time window.")
    _add_read_args(subreddit)
    _add_limit_args(subreddit)
    _add_date_args(subreddit)

    post = commands.add_parser("post", help="Read one post and its comment tree.")
    post.add_argument("identifier", help="Post ID or URL.")
    post.add_argument(
        "--comment-sort",
        choices=["confidence", "top", "best", "new", "controversial", "old", "qa"],
        default="confidence",
        help="Comment sort order.",
    )
    post.add_argument("--depth", type=int, default=None, help="Maximum comment-tree depth.")
    post.add_argument(
        "--comment-limit", type=int, default=500, help="Maximum comments to materialize."
    )
    _add_read_args(post)

    user = commands.add_parser("user", help="Read a redditor's activity.")
    user.add_argument("name", help="Redditor name or URL.")
    user.add_argument(
        "--type",
        choices=["overview", "submitted", "comments", "top"],
        default="overview",
        help="Activity listing type.",
    )
    user.add_argument(
        "--sort",
        choices=["new", "hot", "top", "controversial"],
        default=None,
        help="Listing sort order.",
    )
    user.add_argument("--time", choices=_TIME_CHOICES, default=None, help="Sort time window.")
    _add_read_args(user)
    _add_limit_args(user)
    _add_date_args(user)

    search = commands.add_parser("search", help="Search Reddit.")
    search.add_argument("query", help="Search query.")
    search.add_argument("--subreddit", default=None, help="Restrict results to a subreddit.")
    search.add_argument(
        "--type", choices=["link", "sr", "user"], default="link", help="Search result type."
    )
    search.add_argument(
        "--sort",
        choices=["relevance", "hot", "top", "new", "comments"],
        default=None,
        help="Search sort order.",
    )
    search.add_argument("--time", choices=_TIME_CHOICES, default=None, help="Sort time window.")
    _add_read_args(search)
    _add_limit_args(search)
    _add_date_args(search)

    subreddits = commands.add_parser("subreddits", help="Find subreddits by name or topic.")
    subreddits.add_argument("query", help="Subreddit search query.")
    _add_read_args(subreddits)
    _add_limit_args(subreddits)

    subreddit_info = commands.add_parser("subreddit-info", help="Read subreddit metadata.")
    subreddit_info.add_argument("name", help="Subreddit name or URL.")
    _add_read_args(subreddit_info)
    return parser


_COMMAND_OUTPUT: dict[str, str] = {
    "subreddit": "Post",
    "post": "Post | Comment",
    "user": "Post | Comment",
    "search": "Post | Subreddit | User",
    "subreddits": "Subreddit",
    "subreddit-info": "Subreddit",
}


def _catalog_type(action: argparse.Action) -> str:
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return "boolean"
    if action.type is _parse_iso_date:
        return "date"
    if action.type is int:
        return "integer"
    if action.type is float:
        return "number"
    return getattr(action.type, "__name__", "string") if action.type else "string"


def _argument_catalog(parser: argparse.ArgumentParser) -> list[dict[str, Any]]:
    return [
        {
            "name": action.dest,
            "flags": list(action.option_strings),
            "type": _catalog_type(action),
            "positional": not action.option_strings,
            "required": action.required,
            "default": action.default,
            "choices": list(action.choices) if action.choices is not None else None,
            "is_flag": isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)),
            "help": action.help,
        }
        for action in parser._actions
        if not isinstance(action, argparse._HelpAction)
    ]


def build_catalog() -> dict[str, Any]:
    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    summaries = {item.dest: item.help or "" for item in subparsers._choices_actions}
    return {
        "catalog_version": CATALOG_VERSION,
        "package": "agentic-reddit",
        "command": "agentic-reddit",
        "version": __version__,
        "commands": [
            {
                "name": name,
                "help": subparser.description or summaries.get(name, ""),
                "output": _COMMAND_OUTPUT.get(name),
                "arguments": _argument_catalog(subparser),
            }
            for name, subparser in subparsers.choices.items()
        ],
        "exit_codes": {str(code): text for code, text in errors.EXIT_CODES.items()},
        "output_schema": "agentic-reddit schema --json",
    }


def _cmd_catalog(args: argparse.Namespace) -> int:
    print(json.dumps(build_catalog(), indent=None if args.json else 2, ensure_ascii=False))
    return 0


def _cmd_schema(args: argparse.Namespace) -> int:
    print(json.dumps(model.json_schema(), indent=None if args.json else 2, ensure_ascii=False))
    return 0


def _cmd_setup(args: argparse.Namespace) -> int:
    from . import session

    session.run_setup(
        args.profile,
        profile_dir_override=args.profile_dir,
        force=args.force,
        headed=args.headed,
        timeout_seconds=args.timeout_seconds,
    )
    print("Browser provisioned.", file=sys.stderr)
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    from . import session

    result = session.run_status(args.profile, profile_dir_override=args.profile_dir)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print("ready" if result["ready"] else "setup required", file=sys.stderr)
    return 0 if result["ready"] else 2


def _cmd_doctor(args: argparse.Namespace) -> int:
    from . import session

    result = session.run_doctor(args.profile, profile_dir_override=args.profile_dir)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    return 0


def _safe_identifier(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return safe[:96] or "reddit"


def _output_path(identifier: str, args: argparse.Namespace) -> Path:
    if args.output:
        return Path(args.output).expanduser()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    extension = "ndjson" if args.format == "ndjson" else "json"
    return config.default_output_dir() / f"{_safe_identifier(identifier)}-{stamp}.{extension}"


def _redact_raw_attachments(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: redact.redact(item) if key == "raw" else _redact_raw_attachments(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_raw_attachments(item) for item in value]
    return value


def _write_rows(rows: Iterable[object], path: Path, fmt: str, *, redact_raw: bool = False) -> None:
    data = [item.to_dict() if hasattr(item, "to_dict") else item for item in rows]
    if redact_raw:
        data = [_redact_raw_attachments(row) for row in data]
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=".ar-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            if fmt == "ndjson":
                for row in data:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            else:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        temporary.replace(path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _display_path(path: Path) -> str:
    def escape(character: str) -> str:
        if unicodedata.category(character) not in {"Cc", "Cf"}:
            return character
        codepoint = ord(character)
        if codepoint <= 0xFF:
            return f"\\x{codepoint:02x}"
        if codepoint <= 0xFFFF:
            return f"\\u{codepoint:04x}"
        return f"\\U{codepoint:08x}"

    return "".join(escape(character) for character in str(path))


def _item_summary(items: list[object], command: str, search_type: str | None = None) -> str:
    if command in {"post", "user"}:
        counts = [
            (sum(isinstance(item, model.Post) for item in items), "post"),
            (sum(isinstance(item, model.Comment) for item in items), "comment"),
        ]
        summary = ", ".join(
            f"{count} {label}{'' if count == 1 else 's'}" for count, label in counts if count
        )
        return summary or f"{len(items)} posts"
    labels = {
        "subreddit": "posts",
        "search": {"link": "posts", "sr": "subreddits", "user": "users"}[search_type or "link"],
        "subreddits": "subreddits",
        "subreddit-info": "subreddits",
    }
    return f"{len(items)} {labels[command]}"


def _finish(result: Any, identifier: str, args: argparse.Namespace) -> int:
    items = list(result.items)
    path = _output_path(identifier, args)
    _write_rows(items, path, args.format, redact_raw=args.raw and not args.no_redact)
    timestamps = [
        item.created_at for item in items if getattr(item, "created_at", None) is not None
    ]
    oldest, newest = (
        (min(timestamps).isoformat(), max(timestamps).isoformat())
        if timestamps
        else ("none", "none")
    )
    remaining = getattr(result, "remaining", None)
    reset = getattr(result, "reset", None)
    used = getattr(result, "used", None)
    budget = (
        f"{remaining}/{used}"
        if remaining is not None and reset is not None and used is not None
        else "unknown/unknown"
    )
    print(
        f"{_item_summary(items, args.command, getattr(args, 'type', None))}, "
        f"range {oldest}..{newest}, stop reason: {result.stop_reason}, "
        f"budget {budget}. Saved to {_display_path(path)}",
        file=sys.stderr,
    )
    if getattr(args, "since", None) is not None and not getattr(
        result, "since_target_crossed", False
    ):
        return 7
    return 3 if result.stop_reason == "rate_limited" else 0


def _read_bounds(args: argparse.Namespace) -> tuple[datetime | None, datetime | None]:
    since = datetime.combine(args.since, datetime.min.time(), tzinfo=UTC) if args.since else None
    until = datetime.combine(args.until, datetime.max.time(), tzinfo=UTC) if args.until else None
    return since, until


def _with_browser(args: argparse.Namespace, operation: Callable[[Any], Any]) -> Any:
    from . import pacing, session

    governor = pacing.PacingGovernor(
        wait_on_limit=args.wait_on_limit,
        max_wait=args.max_wait,
    )
    with session.BrowserSession(
        args.profile, profile_dir_override=args.profile_dir, pacing=governor
    ) as browser:
        result = operation(browser)
        result.remaining = browser.pacing.remaining
        result.used = browser.pacing.used
        result.reset = browser.pacing.reset
        return result


def _cmd_subreddit(args: argparse.Namespace) -> int:
    from . import retrieve

    _, subreddit = identity.normalize_subreddit_identifier(args.name)
    since, until = _read_bounds(args)
    result = _with_browser(
        args,
        lambda browser: retrieve.fetch_subreddit(
            browser,
            subreddit,
            sort=args.sort,
            time=args.time,
            limit=args.limit,
            since=since,
            until=until,
            max_requests=config.DEFAULT_MAX_REQUESTS,
            raw=args.raw,
        ),
    )
    return _finish(result, subreddit, args)


def _cmd_post(args: argparse.Namespace) -> int:
    from . import retrieve

    _, post_id = identity.normalize_post_identifier(args.identifier)
    result = _with_browser(
        args,
        lambda browser: retrieve.fetch_post(
            browser,
            post_id,
            comment_sort=args.comment_sort,
            depth=args.depth,
            comment_limit=args.comment_limit,
            max_requests=config.DEFAULT_MAX_REQUESTS,
            raw=args.raw,
        ),
    )
    return _finish(result, post_id, args)


def _cmd_user(args: argparse.Namespace) -> int:
    from . import retrieve

    _, user = identity.normalize_user_identifier(args.name)
    since, until = _read_bounds(args)
    result = _with_browser(
        args,
        lambda browser: retrieve.fetch_user(
            browser,
            user,
            listing_type=args.type,
            sort=args.sort,
            time=args.time,
            limit=args.limit,
            since=since,
            until=until,
            max_requests=config.DEFAULT_MAX_REQUESTS,
            raw=args.raw,
        ),
    )
    return _finish(result, user, args)


def _cmd_search(args: argparse.Namespace) -> int:
    from . import retrieve

    since, until = _read_bounds(args)
    result = _with_browser(
        args,
        lambda browser: retrieve.search(
            browser,
            args.query,
            subreddit=args.subreddit,
            search_type=args.type,
            sort=args.sort,
            time=args.time,
            limit=args.limit,
            since=since,
            until=until,
            max_requests=config.DEFAULT_MAX_REQUESTS,
            raw=args.raw,
        ),
    )
    return _finish(result, args.query, args)


def _cmd_subreddits(args: argparse.Namespace) -> int:
    from . import retrieve

    result = _with_browser(
        args,
        lambda browser: retrieve.find_subreddits(
            browser,
            args.query,
            limit=args.limit,
            max_requests=config.DEFAULT_MAX_REQUESTS,
            raw=args.raw,
        ),
    )
    return _finish(result, args.query, args)


def _cmd_subreddit_info(args: argparse.Namespace) -> int:
    from . import retrieve

    _, subreddit = identity.normalize_subreddit_identifier(args.name)
    result = _with_browser(
        args,
        lambda browser: retrieve.fetch_subreddit_info(
            browser, subreddit, max_requests=config.DEFAULT_MAX_REQUESTS, raw=args.raw
        ),
    )
    return _finish(result, subreddit, args)


_HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "setup": _cmd_setup,
    "status": _cmd_status,
    "doctor": _cmd_doctor,
    "catalog": _cmd_catalog,
    "schema": _cmd_schema,
    "subreddit": _cmd_subreddit,
    "post": _cmd_post,
    "user": _cmd_user,
    "search": _cmd_search,
    "subreddits": _cmd_subreddits,
    "subreddit-info": _cmd_subreddit_info,
}


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if hasattr(args, "limit") and args.limit is not None and args.limit < 0:
        parser.error("--limit must be non-negative")
    for name in ("depth", "comment_limit"):
        value = getattr(args, name, None)
        if value is not None and value < 0:
            parser.error(f"--{name.replace('_', '-')} must be non-negative")
    max_wait = getattr(args, "max_wait", None)
    if max_wait is not None and (not math.isfinite(max_wait) or max_wait < 0):
        parser.error("--max-wait must be a finite non-negative number")
    if max_wait is not None and not args.wait_on_limit:
        parser.error("--max-wait requires --wait-on-limit")
    if getattr(args, "no_redact", False) and not args.raw:
        parser.error("--no-redact requires --raw")
    if getattr(args, "since", None) and getattr(args, "until", None) and args.since > args.until:
        parser.error("--since must not be later than --until")
    if (
        getattr(args, "command", None) == "search"
        and getattr(args, "type", None) != "link"
        and (getattr(args, "since", None) or getattr(args, "until", None))
    ):
        parser.error("--since and --until are only supported for --type link")
    timeout = getattr(args, "timeout_seconds", None)
    if timeout is not None and (not math.isfinite(timeout) or timeout < 0):
        parser.error("--timeout-seconds must be a finite non-negative number")


def _scrub_diagnostic(value: object, *, path_values: Iterable[object] = ()) -> str:
    return redact.scrub_diagnostic(value, path_values=path_values)


def _report_exception(exc: Exception, args: argparse.Namespace) -> int:
    message = _scrub_diagnostic(
        exc,
        path_values=(getattr(args, "profile_dir", None), getattr(args, "output", None)),
    )
    if isinstance(exc, errors.AgenticRedditError):
        print(message, file=sys.stderr)
        return exc.exit_code
    print(
        f"command failed: {message}" if getattr(args, "verbose", False) else "command failed",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_args(parser, args)
    if getattr(args, "no_redact", False):
        print("warning: --no-redact may write sensitive raw data", file=sys.stderr)
    try:
        return _HANDLERS[args.command](args)
    except Exception as exc:
        return _report_exception(exc, args)


if __name__ == "__main__":
    raise SystemExit(main())
