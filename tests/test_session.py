from __future__ import annotations

import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from agentic_reddit import session
from agentic_reddit.errors import (
    BrowserNotReadyError,
    BrowserSetupError,
    ChallengeError,
    EnvelopeParseError,
    NotFoundError,
    RateLimitedError,
    SetupRequiredError,
    TargetUnavailableError,
)


class FakeProcess:
    def __init__(self) -> None:
        self.terminated = 0
        self.killed = 0
        self.waited = 0
        self.running = True

    def poll(self):
        return None if self.running else 0

    def terminate(self) -> None:
        self.terminated += 1
        self.running = False

    def kill(self) -> None:
        self.killed += 1
        self.running = False

    def wait(self, timeout: float) -> None:
        self.waited += 1


class FakePage:
    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.gotos: list[str] = []
        self.evaluations: list[tuple[str, str]] = []
        self.closed = 0

    def goto(self, url: str) -> None:
        self.gotos.append(url)

    def evaluate(self, script: str, path: str):
        assert "fetch(path" in script
        self.evaluations.append((script, path))
        return self.results.pop(0)

    def close(self) -> None:
        self.closed += 1


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.new_page_calls = 0

    def new_page(self) -> FakePage:
        self.new_page_calls += 1
        return self.page


class FakeDynamicSession:
    def __init__(self, results: list[object]) -> None:
        self.page = FakePage(results)
        self.context = FakeContext(self.page)
        self.entered = 0
        self.exited = 0

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, *_: object) -> None:
        self.exited += 1


class FakePacing:
    def __init__(self) -> None:
        self.before = 0
        self.observed: list[tuple[dict[str, str], int | None]] = []

    def before_request(self) -> None:
        self.before += 1

    def observe_response(self, headers, status_code=None) -> None:
        self.observed.append((dict(headers or {}), status_code))
        if status_code == 429:
            raise RateLimitedError()


def response(
    body: str,
    *,
    status: int = 200,
    content_type: str = "application/json",
    headers=None,
):
    return {
        "status": status,
        "contentType": content_type,
        "headers": headers or {},
        "text": body,
    }


def configured_browser(monkeypatch: pytest.MonkeyPatch, results: list[object]):
    process = FakeProcess()
    dynamic = FakeDynamicSession(results)
    monkeypatch.setattr(session, "locate_chrome", lambda: Path("/isolated/chrome"))
    monkeypatch.setattr(session, "_free_loopback_port", lambda: 9222)
    monkeypatch.setattr(
        session,
        "_cdp_websocket_url",
        lambda *args, **kwargs: "ws://127.0.0.1:9222/devtools/browser/test",
    )
    monkeypatch.setattr(session, "_dynamic_session", lambda url: dynamic)
    return process, dynamic


def configured_status(
    monkeypatch: pytest.MonkeyPatch,
    body: object,
    pacing: FakePacing | None = None,
):
    instances = []

    class FakeStatusSession:
        def __init__(self, profile: str, *, profile_dir_override: Path) -> None:
            self.profile = profile
            self.profile_dir_override = profile_dir_override
            self.pacing = pacing or FakePacing()
            self.paths: list[str] = []
            self.exited = 0
            instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            self.exited += 1

        def get_json(self, path: str) -> object:
            self.paths.append(path)
            if isinstance(body, BaseException):
                raise body
            return body

    monkeypatch.setattr(session, "BrowserSession", FakeStatusSession)
    return instances


def warmed_profile(tmp_path: Path, profile: str = "default") -> None:
    (tmp_path / profile / "browser").mkdir(parents=True)


def test_cdp_discovery_uses_loopback_websocket(monkeypatch: pytest.MonkeyPatch):
    payload = b'{"webSocketDebuggerUrl":"ws://127.0.0.1:9222/devtools/browser/test"}'

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def read(self) -> bytes:
            return payload

    monkeypatch.setattr(session, "urlopen", lambda *args, **kwargs: Response())
    discovered = session._cdp_websocket_url(
        9222,
        timeout_seconds=0,
        clock=lambda: 0,
        sleeper=lambda _: None,
    )
    assert discovered.endswith("/test")
    assert not session._is_loopback_websocket(
        "ws://example.com:9222/devtools/browser/test",
        9222,
    )


def test_start_uses_minimal_owned_chrome_and_lazy_scrapling(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    process, dynamic = configured_browser(monkeypatch, [])
    arguments: list[str] = []
    popen_kwargs: dict[str, object] = {}

    def popen(command, **kwargs):
        arguments.extend(command)
        popen_kwargs.update(kwargs)
        return process

    browser = session.BrowserSession(profile_dir_override=tmp_path, popen_factory=popen)
    assert "scrapling.fetchers" not in sys.modules
    browser._start()
    assert arguments[1:] == [
        f"--user-data-dir={tmp_path / 'default' / 'browser'}",
        "--remote-debugging-address=127.0.0.1",
        "--remote-debugging-port=9222",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-first-run-ui",
        "--headless=new",
    ]
    assert popen_kwargs == {
        "stdout": session.subprocess.DEVNULL,
        "stderr": session.subprocess.DEVNULL,
    }
    assert dynamic.entered == 1
    browser.close()


def test_dynamic_session_suppresses_scrapling_info_logs(monkeypatch: pytest.MonkeyPatch):
    class DynamicSession:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class FakeLogger:
        def __init__(self) -> None:
            self.level: int | None = None

        def setLevel(self, level: int) -> None:
            self.level = level

    logger = FakeLogger()
    scrapling = types.ModuleType("scrapling")
    fetchers = types.ModuleType("scrapling.fetchers")
    fetchers.DynamicSession = DynamicSession
    scrapling.fetchers = fetchers
    monkeypatch.setitem(sys.modules, "scrapling", scrapling)
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", fetchers)
    real_get_logger = session.logging.getLogger
    monkeypatch.setattr(
        session.logging,
        "getLogger",
        lambda name=None: logger if name == "scrapling" else real_get_logger(name),
    )

    dynamic = session._dynamic_session("ws://127.0.0.1:9222/devtools/browser/test")

    assert logger.level == session.logging.WARNING
    assert dynamic.kwargs == {
        "cdp_url": "ws://127.0.0.1:9222/devtools/browser/test",
        "max_pages": 1,
    }


def test_warm_polls_until_listing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    process, dynamic = configured_browser(
        monkeypatch,
        [
            response("<html>challenge</html>", content_type="text/html"),
            response('{"kind":"Listing","data":{}}'),
        ],
    )
    pacing = FakePacing()
    browser = session.BrowserSession(
        profile_dir_override=tmp_path,
        pacing=pacing,
        clock=iter([0, 0, 0, 1, 1]).__next__,
        sleeper=lambda _: None,
        popen_factory=lambda *_args, **_kwargs: process,
    )
    browser.warm()
    assert pacing.before == 2
    assert dynamic.context.new_page_calls == 1
    assert dynamic.page.gotos == ["https://www.reddit.com/"]
    assert [path for _, path in dynamic.page.evaluations] == ["/.json", "/.json"]
    browser.close()


def test_warm_times_out_after_challenge(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    process, _ = configured_browser(
        monkeypatch,
        [
            response("blocked", content_type="text/html"),
            response("blocked", content_type="text/html"),
        ],
    )
    clock = iter([0, 0, 0, 1]).__next__
    browser = session.BrowserSession(
        profile_dir_override=tmp_path,
        pacing=FakePacing(),
        warm_timeout_seconds=1,
        clock=clock,
        sleeper=lambda _: None,
        popen_factory=lambda *_args, **_kwargs: process,
    )
    with pytest.raises(SetupRequiredError):
        browser.warm()
    browser.close()


@pytest.mark.parametrize(
    ("result", "error"),
    [
        (response("<html>challenge</html>", content_type="text/html"), ChallengeError),
        (response('{"reason":"Not Found"}', status=404), NotFoundError),
        (response('{"reason":"private"}', status=403), TargetUnavailableError),
        (response("{}", status=429), RateLimitedError),
        (response("{}", status="200"), ChallengeError),
    ],
)
def test_get_json_maps_response_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    result,
    error,
):
    process, _ = configured_browser(monkeypatch, [result])
    browser = session.BrowserSession(
        profile_dir_override=tmp_path,
        pacing=FakePacing(),
        popen_factory=lambda *_args, **_kwargs: process,
    )
    with pytest.raises(error) as exc_info:
        browser.get_json("/r/python/hot.json")
    if error is ChallengeError:
        assert exc_info.value.exit_code == 4
    browser.close()


def test_get_json_returns_body_and_observes_rate_headers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    process, _ = configured_browser(
        monkeypatch,
        [
            response(
                '{"kind":"Listing","data":{}}',
                headers={
                    "x-ratelimit-remaining": "99",
                    "x-ratelimit-reset": "600",
                    "x-ratelimit-used": "1",
                },
            )
        ],
    )
    pacing = FakePacing()
    browser = session.BrowserSession(
        profile_dir_override=tmp_path,
        pacing=pacing,
        popen_factory=lambda *_args, **_kwargs: process,
    )
    assert browser.get_json("/r/python/hot.json") == {"kind": "Listing", "data": {}}
    assert pacing.before == 1
    assert pacing.observed == [
        (
            {
                "x-ratelimit-remaining": "99",
                "x-ratelimit-reset": "600",
                "x-ratelimit-used": "1",
            },
            200,
        )
    ]
    browser.close()


def test_get_json_reuses_one_context_owned_page_for_endpoints_and_pagination(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    process, dynamic = configured_browser(
        monkeypatch,
        [
            response('{"kind":"Listing","data":{}}'),
            response('{"kind":"Listing","data":{"after":"next"}}'),
            response('{"kind":"Listing","data":{}}'),
        ],
    )
    browser = session.BrowserSession(
        profile_dir_override=tmp_path,
        pacing=FakePacing(),
        popen_factory=lambda *_args, **_kwargs: process,
    )

    assert browser.get_json("/r/python/hot.json?limit=1") == {
        "kind": "Listing",
        "data": {},
    }
    assert browser.get_json("/r/python/hot.json?limit=1&after=next") == {
        "kind": "Listing",
        "data": {"after": "next"},
    }
    assert browser.get_json("/user/spez/overview.json?limit=1") == {
        "kind": "Listing",
        "data": {},
    }

    assert dynamic.context.new_page_calls == 1
    assert dynamic.page.gotos == ["https://www.reddit.com/"]
    assert [path for _, path in dynamic.page.evaluations] == [
        "/r/python/hot.json?limit=1",
        "/r/python/hot.json?limit=1&after=next",
        "/user/spez/overview.json?limit=1",
    ]
    browser.close()


def test_get_json_requires_a_context_owned_page(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    process, dynamic = configured_browser(monkeypatch, [])
    dynamic.context = None
    browser = session.BrowserSession(
        profile_dir_override=tmp_path,
        pacing=FakePacing(),
        popen_factory=lambda *_args, **_kwargs: process,
    )

    with pytest.raises(BrowserNotReadyError):
        browser.get_json("/r/python/hot.json")

    browser.close()


def test_close_is_idempotent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    process, dynamic = configured_browser(monkeypatch, [response("{}")])
    browser = session.BrowserSession(
        profile_dir_override=tmp_path,
        pacing=FakePacing(),
        popen_factory=lambda *_args, **_kwargs: process,
    )
    browser.get_json("/r/python/hot.json")
    browser.close()
    browser.close()
    assert dynamic.exited == 1
    assert dynamic.page.closed == 1
    assert process.terminated == 1
    assert browser._page is None


def test_status_requires_an_existing_warmed_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(
        session,
        "BrowserSession",
        lambda *args, **kwargs: pytest.fail("status must not launch a browser"),
    )

    with pytest.raises(SetupRequiredError):
        session.run_status(profile_dir_override=tmp_path)


def test_status_preserves_missing_browser_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    warmed_profile(tmp_path)
    monkeypatch.setattr(
        session,
        "locate_chrome",
        lambda: (_ for _ in ()).throw(BrowserNotReadyError("browser missing")),
    )

    with pytest.raises(BrowserNotReadyError):
        session.run_status(profile_dir_override=tmp_path)


def test_status_translates_challenge_to_setup_required(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    warmed_profile(tmp_path)
    challenge = ChallengeError("challenge")
    configured_status(monkeypatch, challenge)

    with pytest.raises(SetupRequiredError) as exc_info:
        session.run_status(profile_dir_override=tmp_path)

    assert exc_info.value.__cause__ is challenge


def test_status_reads_live_t5_envelope_and_rate_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    warmed_profile(tmp_path)
    pacing = FakePacing()
    pacing.remaining = 99.0
    pacing.reset = 600.0
    pacing.used = 1.0
    instances = configured_status(
        monkeypatch,
        {"kind": "t5", "data": {"display_name": "announcements"}},
        pacing,
    )

    result = session.run_status(profile_dir_override=tmp_path)

    assert result == {"ready": True, "remaining": 99.0, "reset": 600.0, "used": 1.0}
    assert len(instances) == 1
    assert instances[0].paths == ["/r/announcements/about.json"]


def test_status_rejects_an_invalid_t5_envelope(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    warmed_profile(tmp_path)
    instances = configured_status(monkeypatch, {"kind": "t5", "data": []})

    with pytest.raises(EnvelopeParseError):
        session.run_status(profile_dir_override=tmp_path)

    assert instances[0].paths == ["/r/announcements/about.json"]
    assert instances[0].exited == 1


def test_status_closes_its_browser_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    warmed_profile(tmp_path)
    instances = configured_status(monkeypatch, {"kind": "t5", "data": {}})

    session.run_status(profile_dir_override=tmp_path)

    assert instances[0].exited == 1


@pytest.mark.parametrize(
    "layout",
    [
        "chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
        "chrome-linux64/chrome",
        "chrome-win64/chrome.exe",
    ],
)
def test_locate_chrome_supports_platform_cache_layouts(tmp_path: Path, layout: str):
    executable = tmp_path / layout
    executable.parent.mkdir(parents=True)
    executable.write_text("")
    if executable.suffix.casefold() != ".exe":
        executable.chmod(0o700)

    assert session.locate_chrome(tmp_path) == executable


def test_isolated_browser_cache_restores_playwright_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    browser_cache = tmp_path / "browsers"
    monkeypatch.setattr(session.config, "browsers_dir", lambda: browser_cache)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "/previous")

    with session._isolated_browser_cache():
        assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(browser_cache)

    assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == "/previous"


def test_isolated_browser_cache_removes_temporary_playwright_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    browser_cache = tmp_path / "browsers"
    monkeypatch.setattr(session.config, "browsers_dir", lambda: browser_cache)
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)

    with session._isolated_browser_cache():
        assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(browser_cache)

    assert "PLAYWRIGHT_BROWSERS_PATH" not in os.environ


def test_run_setup_passes_force_to_installer_and_restores_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    browser_cache = tmp_path / "browsers"
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(session.config, "browsers_dir", lambda: browser_cache)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "/previous")

    installer = types.ModuleType("scrapling.cli.main")

    def install(**kwargs: object) -> None:
        calls.append({"environment": os.environ["PLAYWRIGHT_BROWSERS_PATH"], **kwargs})

    installer.main = install
    monkeypatch.setitem(sys.modules, "scrapling", types.ModuleType("scrapling"))
    monkeypatch.setitem(sys.modules, "scrapling.cli", types.ModuleType("scrapling.cli"))
    monkeypatch.setitem(sys.modules, "scrapling.cli.main", installer)

    class FakeSetupSession:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def warm(self) -> dict[str, object]:
            return {"kind": "Listing", "data": {}}

    monkeypatch.setattr(session, "BrowserSession", FakeSetupSession)
    session.run_setup(force=True, profile_dir_override=tmp_path)

    assert calls == [
        {
            "environment": str(browser_cache),
            "args": ["install", "--force"],
            "prog_name": "scrapling",
            "standalone_mode": False,
        }
    ]
    assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == "/previous"


def test_run_setup_wraps_installer_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    installer = types.ModuleType("scrapling.cli.main")
    installer.main = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("failed"))
    monkeypatch.setitem(sys.modules, "scrapling", types.ModuleType("scrapling"))
    monkeypatch.setitem(sys.modules, "scrapling.cli", types.ModuleType("scrapling.cli"))
    monkeypatch.setitem(sys.modules, "scrapling.cli.main", installer)
    monkeypatch.setattr(session.config, "browsers_dir", lambda: tmp_path / "browsers")

    with pytest.raises(BrowserSetupError):
        session.run_setup(profile_dir_override=tmp_path)


def test_doctor_preserves_missing_browser_and_profile_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(
        session,
        "locate_chrome",
        lambda: (_ for _ in ()).throw(BrowserNotReadyError("browser missing")),
    )
    with pytest.raises(BrowserNotReadyError):
        session.run_doctor(profile_dir_override=tmp_path)

    monkeypatch.setattr(session, "locate_chrome", lambda: Path("/isolated/chrome"))
    monkeypatch.setattr(
        session,
        "BrowserSession",
        lambda *args, **kwargs: pytest.fail("doctor must not launch without a profile"),
    )
    with pytest.raises(SetupRequiredError):
        session.run_doctor(profile_dir_override=tmp_path)


def test_doctor_translates_warm_challenge_timeout_and_closes_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    warmed_profile(tmp_path)
    process, dynamic = configured_browser(
        monkeypatch,
        [response("blocked", content_type="text/html")],
    )
    browser_session = session.BrowserSession
    instances = []

    def create_browser_session(*args: object, **kwargs: object):
        browser = browser_session(
            *args,
            **kwargs,
            warm_timeout_seconds=0,
            popen_factory=lambda *_args, **_kwargs: process,
        )
        instances.append(browser)
        return browser

    monkeypatch.setattr(session, "BrowserSession", create_browser_session)

    with pytest.raises(SetupRequiredError) as exc_info:
        session.run_doctor(profile_dir_override=tmp_path)

    assert exc_info.value.exit_code == 2
    assert len(instances) == 1
    assert dynamic.exited == 1
    assert dynamic.page.closed == 1
    assert process.terminated == 1


def test_doctor_preserves_non_challenge_round_trip_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    warmed_profile(tmp_path)
    process, dynamic = configured_browser(
        monkeypatch,
        [response('{"kind": "Listing", "data": []}')],
    )
    browser_session = session.BrowserSession
    instances = []

    def create_browser_session(*args: object, **kwargs: object):
        browser = browser_session(
            *args,
            **kwargs,
            warm_timeout_seconds=0,
            popen_factory=lambda *_args, **_kwargs: process,
        )
        instances.append(browser)
        return browser

    monkeypatch.setattr(session, "BrowserSession", create_browser_session)

    with pytest.raises(EnvelopeParseError) as exc_info:
        session.run_doctor(profile_dir_override=tmp_path)

    assert exc_info.value.exit_code == 4
    assert len(instances) == 1
    assert dynamic.exited == 1
    assert dynamic.page.closed == 1
    assert process.terminated == 1


def test_doctor_reports_listing_and_rate_budget(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    warmed_profile(tmp_path)
    monkeypatch.setattr(session, "locate_chrome", lambda: Path("/isolated/chrome"))

    class FakeDoctorSession:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.pacing = types.SimpleNamespace(remaining=99.0, reset=600.0, used=1.0)

        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def warm(self) -> dict[str, object]:
            return {"kind": "Listing", "data": {}}

    monkeypatch.setattr(session, "BrowserSession", FakeDoctorSession)

    assert session.run_doctor(profile_dir_override=tmp_path) == {
        "browser_executable": True,
        "profile": True,
        "listing": True,
        "rate_budget": {"remaining": 99.0, "reset": 600.0, "used": 1.0},
    }


def test_close_records_warning_when_owned_process_survives_kill():
    class StubbornProcess:
        def __init__(self) -> None:
            self.terminated = 0
            self.killed = 0

        def poll(self):
            return None

        def terminate(self) -> None:
            self.terminated += 1

        def kill(self) -> None:
            self.killed += 1

        def wait(self, timeout: float) -> None:
            raise subprocess.TimeoutExpired("chrome", timeout)

    browser = session.BrowserSession()
    process = StubbornProcess()
    browser._process = process
    browser.close()

    assert process.terminated == 1
    assert process.killed == 1
    assert browser.cleanup_warning == "owned Chrome process did not exit after kill"


def test_close_kills_and_reaps_when_terminate_raises():
    class TerminateFailingProcess:
        def __init__(self) -> None:
            self.terminated = 0
            self.killed = 0
            self.wait_timeouts: list[float] = []
            self.running = True

        def poll(self):
            return None if self.running else 0

        def terminate(self) -> None:
            self.terminated += 1
            raise OSError("terminate failed")

        def kill(self) -> None:
            self.killed += 1
            self.running = False

        def wait(self, timeout: float) -> None:
            self.wait_timeouts.append(timeout)

    browser = session.BrowserSession()
    process = TerminateFailingProcess()
    browser._process = process
    browser.close()
    browser.close()

    assert process.terminated == 1
    assert process.killed == 1
    assert process.wait_timeouts == [5]
    assert browser.cleanup_warning is None


def test_close_reaps_after_kill_raises():
    class KillFailingProcess:
        def __init__(self) -> None:
            self.terminated = 0
            self.killed = 0
            self.wait_timeouts: list[float] = []
            self.running = True

        def poll(self):
            return None if self.running else 0

        def terminate(self) -> None:
            self.terminated += 1
            raise OSError("terminate failed")

        def kill(self) -> None:
            self.killed += 1
            raise OSError("kill failed")

        def wait(self, timeout: float) -> None:
            self.wait_timeouts.append(timeout)
            self.running = False

    browser = session.BrowserSession()
    process = KillFailingProcess()
    browser._process = process
    browser.close()

    assert process.terminated == 1
    assert process.killed == 1
    assert process.wait_timeouts == [5]
    assert browser.cleanup_warning == "owned Chrome process kill failed"


def test_close_does_not_escalate_when_terminate_exception_stops_process():
    class TerminateStoppingProcess:
        def __init__(self) -> None:
            self.terminated = 0
            self.killed = 0
            self.wait_timeouts: list[float] = []
            self.running = True

        def poll(self):
            return None if self.running else 0

        def terminate(self) -> None:
            self.terminated += 1
            self.running = False
            raise OSError("terminate failed after process exit")

        def kill(self) -> None:
            self.killed += 1

        def wait(self, timeout: float) -> None:
            self.wait_timeouts.append(timeout)

    browser = session.BrowserSession()
    process = TerminateStoppingProcess()
    browser._process = process
    browser.close()

    assert process.terminated == 1
    assert process.killed == 0
    assert process.wait_timeouts == []
    assert browser.cleanup_warning is None


def test_context_manager_preserves_primary_exception_when_cleanup_fails():
    class CleanupFailingProcess:
        def __init__(self) -> None:
            self.wait_timeouts: list[float] = []
            self.running = True

        def poll(self):
            return None if self.running else 0

        def terminate(self) -> None:
            raise OSError("terminate failed")

        def kill(self) -> None:
            raise OSError("kill failed")

        def wait(self, timeout: float) -> None:
            self.wait_timeouts.append(timeout)
            raise OSError("wait failed")

    browser = session.BrowserSession()
    process = CleanupFailingProcess()
    browser._process = process

    with pytest.raises(ValueError, match="primary failure"):
        with browser:
            raise ValueError("primary failure")

    assert process.wait_timeouts == [5]
    assert browser.cleanup_warning == "owned Chrome process exit was not confirmed"
