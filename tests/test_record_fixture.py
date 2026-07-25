from __future__ import annotations

import importlib.util
import stat
import sys
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).parent.parent


def _load_recorder() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "record_fixture.py"
    spec = importlib.util.spec_from_file_location("agentic_reddit_record_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


recorder = _load_recorder()


def _configure_scratch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    scratch = tmp_path / "scratch"
    monkeypatch.setattr(recorder, "SCRATCH_DIR", scratch)
    monkeypatch.setattr(recorder, "FIXTURES_DIR", tmp_path / "fixtures")
    return scratch


def test_write_capture_accepts_safe_name_and_sets_private_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scratch = _configure_scratch(monkeypatch, tmp_path)

    destination = recorder.write_capture("capture-01", b'{"ok": true}')

    assert destination == scratch / "capture-01.raw.json"
    assert destination.read_bytes() == b'{"ok": true}'
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


def test_write_capture_refuses_existing_capture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scratch = _configure_scratch(monkeypatch, tmp_path)
    scratch.mkdir()
    (scratch / "capture.raw.json").write_bytes(b"{}")

    with pytest.raises(recorder.CaptureError, match="refusing to overwrite"):
        recorder.write_capture("capture", b"{}")


def test_write_capture_refuses_symlinked_scratch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    scratch = tmp_path / "scratch"
    scratch.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(recorder, "SCRATCH_DIR", scratch)
    monkeypatch.setattr(recorder, "FIXTURES_DIR", tmp_path / "fixtures")

    with pytest.raises(recorder.CaptureError, match="real directory"):
        recorder.write_capture("capture", b"{}")


def test_write_capture_removes_partial_file_after_write_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scratch = _configure_scratch(monkeypatch, tmp_path)
    monkeypatch.setattr(
        recorder.os,
        "fsync",
        lambda _fd: (_ for _ in ()).throw(OSError("failed")),
    )

    with pytest.raises(OSError, match="failed"):
        recorder.write_capture("capture", b'{"token": "super-secret"}')

    assert not (scratch / "capture.raw.json").exists()


def test_write_capture_chains_cleanup_failure_without_payload_leak(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scratch = _configure_scratch(monkeypatch, tmp_path)
    monkeypatch.setattr(
        recorder.os,
        "fsync",
        lambda _fd: (_ for _ in ()).throw(OSError("write failed")),
    )
    monkeypatch.setattr(
        recorder.os,
        "unlink",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("unlink failed")),
    )

    with pytest.raises(recorder.CaptureError) as raised:
        recorder.write_capture("capture", b'{"token": "super-secret"}')

    error = raised.value
    assert "super-secret" not in str(error)
    assert "scratch/capture.raw.json" in str(error)
    assert isinstance(error.__cause__, OSError)
    assert error.__notes__ == ["primary capture failure: OSError"]
    assert (scratch / "capture.raw.json").exists()
