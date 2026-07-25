"""The minimal browser transport used for anonymous Reddit reads."""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from . import config
from .errors import (
    BrowserNotReadyError,
    BrowserSetupError,
    ChallengeError,
    EnvelopeParseError,
    NotFoundError,
    SetupRequiredError,
    TargetUnavailableError,
)
from .pacing import PacingGovernor

_CDP_HOST = "127.0.0.1"
_CDP_PATH = "/json/version"
_HOME_PATH = "/"
_LISTING_PATH = "/.json"
_RATE_HEADERS = (
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "x-ratelimit-used",
)
_FETCH_SCRIPT = """async (path) => {
    const response = await fetch(path, {headers: {Accept: 'application/json'}});
    const headers = {};
    for (const name of ['x-ratelimit-remaining', 'x-ratelimit-reset', 'x-ratelimit-used']) {
        const value = response.headers.get(name);
        if (value !== null) headers[name] = value;
    }
    return {
        status: response.status,
        contentType: response.headers.get('content-type') || '',
        headers,
        text: await response.text(),
    };
}"""


def locate_chrome(browsers_path: Path | None = None) -> Path:
    """Find an executable Chrome-for-Testing binary in the isolated cache."""
    root = browsers_path or config.browsers_dir()
    if not root.is_dir():
        raise BrowserNotReadyError("browser is not installed; run agentic-reddit setup")

    names = {
        "chrome",
        "chrome.exe",
        "google chrome for testing",
        "google chrome for testing.exe",
    }
    candidates = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.name.casefold() in names
            and (path.suffix.casefold() == ".exe" or os.access(path, os.X_OK))
        ),
        key=lambda path: ("chrome-for-testing" not in str(path).casefold(), len(path.parts)),
    )
    if not candidates:
        raise BrowserNotReadyError("browser is not installed; run agentic-reddit setup")
    return candidates[0]


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((_CDP_HOST, 0))
        return int(listener.getsockname()[1])


def _cdp_websocket_url(
    port: int,
    *,
    timeout_seconds: float,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> str:
    """Wait for Chrome's loopback CDP endpoint and return its WebSocket URL."""
    deadline = clock() + timeout_seconds
    endpoint = f"http://{_CDP_HOST}:{port}{_CDP_PATH}"
    while True:
        try:
            with urlopen(
                endpoint,
                timeout=min(1.0, max(0.1, timeout_seconds)),
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            websocket_url = payload.get("webSocketDebuggerUrl")
            if _is_loopback_websocket(websocket_url, port):
                return websocket_url
        except (OSError, URLError, ValueError, json.JSONDecodeError):
            pass
        if clock() >= deadline:
            raise BrowserNotReadyError("Chrome did not expose its CDP endpoint")
        sleeper(0.1)


def _is_loopback_websocket(value: object, port: int) -> bool:
    if not isinstance(value, str):
        return False
    try:
        endpoint = urlsplit(value)
        endpoint_port = endpoint.port
    except ValueError:
        return False
    return (
        endpoint.scheme == "ws"
        and endpoint.hostname in {_CDP_HOST, "localhost", "::1"}
        and endpoint_port == port
        and bool(endpoint.path)
    )


@contextmanager
def _isolated_browser_cache():
    """Point Scrapling's installer at this package's browser cache only."""
    browser_cache = config.browsers_dir()
    browser_cache.mkdir(parents=True, exist_ok=True)
    previous = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_cache)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
        else:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = previous


class BrowserSession:
    """One owned Chrome subprocess and one attached Scrapling session."""

    def __init__(
        self,
        profile: str = config.DEFAULT_PROFILE_NAME,
        *,
        profile_dir_override: str | Path | None = None,
        headed: bool = False,
        warm_timeout_seconds: float = 60.0,
        pacing: PacingGovernor | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        popen_factory: Callable[..., Any] = subprocess.Popen,
    ) -> None:
        if warm_timeout_seconds < 0:
            raise ValueError("warm_timeout_seconds must be non-negative")
        self.profile = profile
        self.profile_dir_override = profile_dir_override
        self.headed = headed
        self.warm_timeout_seconds = warm_timeout_seconds
        self.pacing = pacing or PacingGovernor()
        self._clock = clock
        self._sleeper = sleeper
        self._popen_factory = popen_factory
        self._process: Any | None = None
        self._session: Any | None = None
        self._entered_session = False
        self._page: Any | None = None
        self.cleanup_warning: str | None = None

    def warm(self) -> dict[str, Any] | list[Any]:
        """Start the transport, load Reddit, and wait for a Listing response."""
        self._start()
        self._capture_home_page()

        deadline = self._clock() + self.warm_timeout_seconds
        while True:
            try:
                body = self.get_json(_LISTING_PATH)
                if _is_listing(body):
                    return body
                raise EnvelopeParseError("Reddit returned an invalid Listing envelope")
            except ChallengeError:
                pass
            if self._clock() >= deadline:
                raise SetupRequiredError(
                    "Reddit challenge did not clear; run agentic-reddit setup again"
                )
            self._sleeper(min(1.0, max(0.0, deadline - self._clock())))

    def get_json(self, path: str) -> dict[str, Any] | list[Any]:
        """Fetch a same-origin JSON endpoint inside the warmed browser page."""
        if not _is_same_origin_path(path):
            raise ValueError("path must be an absolute same-origin path")
        self._start()
        self._capture_home_page()
        self.pacing.before_request()
        result = self._fetch_in_page(path)
        headers = _headers_from(result.get("headers"))
        status = result.get("status")
        if isinstance(status, bool) or not isinstance(status, int):
            raise ChallengeError(
                "Reddit returned an invalid response status; run agentic-reddit setup"
            )
        status_code = status
        self.pacing.observe_response(headers, status_code)

        content_type = result.get("contentType")
        text = result.get("text")
        if not isinstance(content_type, str) or "json" not in content_type.casefold():
            raise ChallengeError(
                "Reddit returned a non-JSON challenge page; run agentic-reddit setup"
            )
        if not isinstance(text, str):
            raise ChallengeError(
                "Reddit returned an invalid JSON response; run agentic-reddit setup"
            )
        try:
            body = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ChallengeError("Reddit returned invalid JSON; run agentic-reddit setup") from exc

        if status_code == 404 or _has_unavailable_shape(body, "not found"):
            raise NotFoundError("Reddit target was not found")
        if status_code == 403 or _has_unavailable_shape(body, "unavailable"):
            raise TargetUnavailableError("Reddit target is unavailable")
        if not isinstance(body, (dict, list)):
            raise ChallengeError(
                "Reddit returned an unexpected JSON body; run agentic-reddit setup"
            )
        return body

    def close(self) -> None:
        """Close the owned page and Scrapling, then this instance's Chrome process."""
        page, self._page = self._page, None
        try:
            if page is not None:
                close_page = getattr(page, "close", None)
                if callable(close_page):
                    close_page()
        except Exception:
            self._record_cleanup_warning("browser page cleanup failed")

        session, self._session = self._session, None
        entered, self._entered_session = self._entered_session, False
        try:
            if session is not None:
                if entered:
                    session.__exit__(None, None, None)
                elif hasattr(session, "close"):
                    session.close()
        except Exception:
            self._record_cleanup_warning("Scrapling session cleanup failed")

        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.poll() is None:
                try:
                    process.terminate()
                except Exception:
                    if process.poll() is None:
                        self._kill_and_wait(process)
                else:
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self._kill_and_wait(process)
        except Exception:
            self._record_cleanup_warning("owned Chrome process exit was not confirmed")

    def __enter__(self) -> BrowserSession:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _kill_and_wait(self, process: Any) -> None:
        """Force a process down and always attempt one bounded reap."""
        kill_failed = False
        try:
            process.kill()
        except Exception:
            kill_failed = True
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            message = (
                "owned Chrome process could not be killed or reaped"
                if kill_failed
                else "owned Chrome process did not exit after kill"
            )
            self._record_cleanup_warning(message)
        except Exception:
            self._record_cleanup_warning("owned Chrome process exit was not confirmed")
        else:
            if kill_failed:
                self._record_cleanup_warning("owned Chrome process kill failed")

    def _record_cleanup_warning(self, message: str) -> None:
        self.cleanup_warning = message
        logging.getLogger(__name__).warning(message)

    def _start(self) -> None:
        if self._session is not None:
            return
        executable = locate_chrome()
        browser_profile = config.browser_profile_dir(
            self.profile,
            profile_dir_override=self.profile_dir_override,
        )
        browser_profile.mkdir(parents=True, exist_ok=True, mode=0o700)
        browser_profile.chmod(0o700)
        port = _free_loopback_port()
        arguments = [
            str(executable),
            f"--user-data-dir={browser_profile}",
            f"--remote-debugging-address={_CDP_HOST}",
            f"--remote-debugging-port={port}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-first-run-ui",
        ]
        if not self.headed:
            arguments.append("--headless=new")
        try:
            self._process = self._popen_factory(
                arguments, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            websocket_url = _cdp_websocket_url(
                port,
                timeout_seconds=self.warm_timeout_seconds,
                clock=self._clock,
                sleeper=self._sleeper,
            )
            self._session = _dynamic_session(websocket_url)
            self._session.__enter__()
            self._entered_session = True
        except Exception:
            self.close()
            raise

    def _capture_home_page(self) -> None:
        assert self._session is not None
        if self._page is not None:
            return

        context = getattr(self._session, "context", None)
        new_page = getattr(context, "new_page", None)
        if not callable(new_page):
            raise BrowserNotReadyError("browser could not create Reddit page")
        try:
            page = new_page()
            navigate = getattr(page, "goto", None)
            if not callable(navigate):
                raise BrowserNotReadyError("browser could not create Reddit page")
            self._page = page
            navigate(config.REDDIT_BASE + _HOME_PATH)
        except Exception as exc:
            raise BrowserNotReadyError("browser could not create Reddit page") from exc

    def _fetch_in_page(self, path: str) -> Mapping[str, Any]:
        if self._page is None:
            raise BrowserNotReadyError("browser could not evaluate Reddit fetch")
        evaluate = getattr(self._page, "evaluate", None)
        if not callable(evaluate):
            raise BrowserNotReadyError("browser could not evaluate Reddit fetch")
        try:
            captured = evaluate(_FETCH_SCRIPT, path)
        except Exception as exc:
            raise BrowserNotReadyError("browser could not evaluate Reddit fetch") from exc
        if not isinstance(captured, Mapping):
            raise BrowserNotReadyError("browser could not evaluate Reddit fetch")
        return captured


def _dynamic_session(websocket_url: str) -> Any:
    """Import Scrapling only when a browser is actually needed."""
    try:
        from scrapling.fetchers import DynamicSession
    except ImportError as exc:
        raise BrowserSetupError(
            "browser support is not installed; run agentic-reddit setup"
        ) from exc
    logging.getLogger("scrapling").setLevel(logging.WARNING)
    return DynamicSession(cdp_url=websocket_url, max_pages=1)


def _is_same_origin_path(path: object) -> bool:
    return isinstance(path, str) and path.startswith("/") and not path.startswith("//")


def _headers_from(headers: object) -> dict[str, str]:
    if not isinstance(headers, Mapping):
        return {}
    return {
        str(name): str(value)
        for name, value in headers.items()
        if str(name).casefold() in _RATE_HEADERS
    }


def _is_listing(body: object) -> bool:
    return (
        isinstance(body, Mapping)
        and body.get("kind") == "Listing"
        and isinstance(body.get("data"), Mapping)
    )


def _is_t5(body: object) -> bool:
    return (
        isinstance(body, Mapping)
        and body.get("kind") == "t5"
        and isinstance(body.get("data"), Mapping)
    )


def _has_unavailable_shape(body: object, kind: str) -> bool:
    if not isinstance(body, Mapping):
        return False
    text = " ".join(
        str(body.get(key, "")) for key in ("reason", "message", "error", "explanation")
    ).casefold()
    if kind == "not found":
        return "not found" in text
    return any(
        word in text
        for word in (
            "forbidden",
            "private",
            "banned",
            "quarantined",
            "suspended",
            "deleted",
        )
    )


def run_setup(
    profile: str = config.DEFAULT_PROFILE_NAME,
    *,
    profile_dir_override: str | Path | None = None,
    headed: bool = False,
    force: bool = False,
    timeout_seconds: float = 120.0,
) -> None:
    """Install Chrome-for-Testing into the isolated cache and warm a profile."""
    with _isolated_browser_cache():
        try:
            from scrapling.cli import main as scrapling_main
        except ImportError as exc:
            raise BrowserSetupError("browser support is not installed") from exc
        arguments = ["install"]
        if force:
            arguments.append("--force")
        try:
            scrapling_main.main(
                args=arguments,
                prog_name="scrapling",
                standalone_mode=False,
            )
        except Exception as exc:
            raise BrowserSetupError(f"browser installation failed: {type(exc).__name__}") from exc
    with BrowserSession(
        profile,
        profile_dir_override=profile_dir_override,
        headed=headed,
        warm_timeout_seconds=timeout_seconds,
    ) as session:
        session.warm()


def run_status(
    profile: str = config.DEFAULT_PROFILE_NAME,
    *,
    profile_dir_override: str | Path | None = None,
) -> dict[str, bool | float | None]:
    """Report live Reddit readiness and the current rate-limit budget."""
    browser_profile = config.browser_profile_dir(
        profile,
        profile_dir_override=profile_dir_override,
    )
    if not browser_profile.is_dir():
        raise SetupRequiredError("browser profile is not warmed; run agentic-reddit setup")

    try:
        with BrowserSession(
            profile,
            profile_dir_override=profile_dir_override,
        ) as browser:
            body = browser.get_json("/r/announcements/about.json")
            if not _is_t5(body):
                raise EnvelopeParseError("Reddit returned an invalid t5 envelope")
            return {
                "ready": True,
                "remaining": getattr(browser.pacing, "remaining", None),
                "reset": getattr(browser.pacing, "reset", None),
                "used": getattr(browser.pacing, "used", None),
            }
    except ChallengeError as exc:
        raise SetupRequiredError("Reddit challenge detected; run agentic-reddit setup") from exc


def run_doctor(
    profile: str = config.DEFAULT_PROFILE_NAME,
    *,
    profile_dir_override: str | Path | None = None,
    headed: bool = False,
) -> dict[str, object]:
    """Check browser, profile, Listing round-trip, and observed rate budget."""
    locate_chrome()
    browser_profile = config.browser_profile_dir(
        profile,
        profile_dir_override=profile_dir_override,
    )
    if not browser_profile.is_dir():
        raise SetupRequiredError("browser profile is not warmed; run agentic-reddit setup")
    with BrowserSession(
        profile,
        profile_dir_override=profile_dir_override,
        headed=headed,
    ) as session:
        listing = session.warm()
        if not _is_listing(listing):
            raise EnvelopeParseError("Reddit returned an invalid Listing envelope")
        return {
            "browser_executable": True,
            "profile": True,
            "listing": True,
            "rate_budget": {
                "remaining": getattr(session.pacing, "remaining", None),
                "reset": getattr(session.pacing, "reset", None),
                "used": getattr(session.pacing, "used", None),
            },
        }
