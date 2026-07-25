"""Offline tests for the release version consistency gate."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_tag_version.py"


def load_gate_module():
    """Load the standalone script without importing ``agentic_reddit``."""
    module_name = "check_tag_version_test_module"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def write_project(
    root: Path,
    *,
    pyproject: str = '[project]\nversion = "0.1.0"\n',
    source: str = '__version__ = "0.1.0"\n',
) -> None:
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    package = root / "src" / "agentic_reddit"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(source, encoding="utf-8")


@pytest.mark.parametrize(
    "source",
    ['__version__ = "0.1.0"\n', '__version__: str = "0.1.0"\n'],
)
def test_source_version_reads_static_assignments(tmp_path: Path, source: str) -> None:
    module = load_gate_module()
    version_file = tmp_path / "__init__.py"
    version_file.write_text(source, encoding="utf-8")

    assert module.source_version(version_file) == "0.1.0"


@pytest.mark.parametrize(
    "source",
    [
        "VERSION = '0.1.0'\n",
        "__version__ = 1\n",
        "__version__ = make_version()\n",
    ],
)
def test_source_version_rejects_missing_or_nonstatic_version(tmp_path: Path, source: str) -> None:
    module = load_gate_module()
    version_file = tmp_path / "__init__.py"
    version_file.write_text(source, encoding="utf-8")

    with pytest.raises(ValueError, match="must define __version__ as a static string"):
        module.source_version(version_file)


def test_source_version_reports_invalid_python(tmp_path: Path) -> None:
    module = load_gate_module()
    version_file = tmp_path / "__init__.py"
    version_file.write_text('__version__ = "unterminated\n', encoding="utf-8")

    with pytest.raises(SyntaxError):
        module.source_version(version_file)


@pytest.mark.parametrize("tag", ["v0.1.0", "0.1.0"])
def test_main_accepts_prefixed_and_bare_matching_tags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tag: str,
) -> None:
    module = load_gate_module()
    write_project(tmp_path)
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)

    assert module.main([tag]) == 0
    assert capsys.readouterr().out == (
        f"OK: tag {tag!r} matches pyproject.toml and agentic_reddit.__version__ ('0.1.0')\n"
    )


@pytest.mark.parametrize(
    ("tag", "pyproject_version", "source_version"),
    [
        ("v0.2.0", "0.1.0", "0.1.0"),
        ("v0.1.0", "0.2.0", "0.1.0"),
        ("v0.1.0", "0.1.0", "0.2.0"),
    ],
)
def test_main_rejects_each_version_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tag: str,
    pyproject_version: str,
    source_version: str,
) -> None:
    module = load_gate_module()
    write_project(
        tmp_path,
        pyproject=f'[project]\nversion = "{pyproject_version}"\n',
        source=f'__version__ = "{source_version}"\n',
    )
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)

    assert module.main([tag]) == 1
    assert capsys.readouterr().err == (
        "::error::release versions do not match across tag, pyproject.toml, "
        "and agentic_reddit.__version__\n"
    )


@pytest.mark.parametrize(
    "pyproject",
    [
        "not valid toml = [\n",
        "[project]\nname = 'agentic-reddit'\n",
        "[project]\nversion = 1\n",
    ],
)
def test_main_rejects_malformed_pyproject_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    pyproject: str,
) -> None:
    module = load_gate_module()
    write_project(tmp_path, pyproject=pyproject)
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)

    assert module.main(["v0.1.0"]) == 1
    assert capsys.readouterr().err == (
        "::error::could not read package versions; check pyproject.toml "
        "[project].version and src/agentic_reddit/__init__.py __version__\n"
    )


def test_main_returns_value_free_diagnostic_for_unreadable_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_gate_module()
    write_project(tmp_path, source='__version__ = "secret-source-version\n')
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)

    assert module.main(["vsecret-tag-version"]) == 1
    diagnostic = capsys.readouterr().err
    assert "check pyproject.toml" in diagnostic
    assert "secret-tag-version" not in diagnostic
    assert "secret-source-version" not in diagnostic


def test_main_returns_value_free_diagnostic_for_version_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_gate_module()
    write_project(
        tmp_path,
        pyproject='[project]\nversion = "secret-pyproject-version"\n',
        source='__version__ = "secret-source-version"\n',
    )
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)

    assert module.main(["vsecret-tag-version"]) == 1
    diagnostic = capsys.readouterr().err
    assert "versions do not match" in diagnostic
    assert "secret-tag-version" not in diagnostic
    assert "secret-pyproject-version" not in diagnostic
    assert "secret-source-version" not in diagnostic
