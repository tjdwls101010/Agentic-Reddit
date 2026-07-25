from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).parent.parent


def _load_scanner() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "check_fixtures_pii.py"
    spec = importlib.util.spec_from_file_location("agentic_reddit_fixture_scanner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scanner = _load_scanner()


def _scan(tmp_path: Path, payload: object) -> list[str]:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return scanner.scan_file(path)


def test_every_committed_fixture_passes_structural_scan():
    assert scanner.scan_fixtures() == []


@pytest.mark.parametrize(
    ("unsafe_payload", "safe_payload", "category"),
    (
        (
            {"api_key": "withheld"},
            {"api_response": "withheld"},
            "credential-key",
        ),
        (
            {"message": "record@fixture.invalid"},
            {"message": "record at fixture dot invalid"},
            "email",
        ),
        (
            {"message": "+1 555-010-1234"},
            {"message": "phone withheld"},
            "phone",
        ),
        (
            {"message": "eyJaaaaaaaaaaaaaaaa.bbbbbbbbbbbbbbbb.cccccccc"},
            {"message": "token withheld"},
            "high-entropy-secret",
        ),
        (
            {"message": "aB3dE5fG7hI9jK1mN2pQ4rS6tU8vW0xY"},
            {"message": "repeated-value-repeated-value"},
            "high-entropy-secret",
        ),
    ),
)
def test_scanner_detects_sensitive_values_and_accepts_safe_counterparts(
    tmp_path, unsafe_payload, safe_payload, category
):
    assert _scan(tmp_path, unsafe_payload) == [f"fixture.json: {category}"]
    assert _scan(tmp_path, safe_payload) == []


def test_scanner_rejects_invalid_json_and_accepts_valid_json(tmp_path):
    path = tmp_path / "fixture.json"
    path.write_text("{not json", encoding="utf-8")

    assert scanner.scan_file(path) == ["fixture.json: invalid-json"]
    assert _scan(tmp_path, {"status": "synthetic fixture"}) == []


def test_scanner_rejects_unsafe_file_inputs(tmp_path):
    missing = tmp_path / "missing.json"
    directory = tmp_path / "directory.json"
    directory.mkdir()
    target = tmp_path / "target.json"
    target.write_text('{"status": "synthetic fixture"}', encoding="utf-8")
    symlink = tmp_path / "linked.json"
    symlink.symlink_to(target)

    for path in (missing, directory, symlink):
        assert scanner.scan_file(path) == [f"{path.name}: unsafe-file"]


def test_scanner_diagnostics_are_deterministic_and_value_free(tmp_path):
    email = "record@fixture.invalid"
    phone = "+1 555-010-1234"
    token = "eyJaaaaaaaaaaaaaaaa.bbbbbbbbbbbbbbbb.cccccccc"
    username = "captured_user"
    payload = {
        "api_key": "withheld",
        "message": f"{email}; {phone}; {token}",
        "author": username,
    }

    diagnostics = _scan(tmp_path, payload)

    assert diagnostics == [
        "fixture.json: credential-key",
        "fixture.json: email",
        "fixture.json: phone",
        "fixture.json: high-entropy-secret",
        "fixture.json: non-synthetic-username",
    ]
    assert all(
        value not in diagnostic
        for value in (email, phone, token, username)
        for diagnostic in diagnostics
    )


@pytest.mark.parametrize(
    "payload",
    (
        {"kind": "t2", "data": {"name": "captured_user"}},
        {"fullname": "t2_account01", "name": "captured_user"},
        {"author_fullname": "t2_captured_user"},
        {"author_url": "https://www.reddit.com/user/captured_user/"},
        {"profile_url": "/u/captured_user/"},
        {"user_url": "https://old.reddit.com/user/captured_user/"},
    ),
)
def test_rejects_captured_looking_reddit_user_identity_fields(tmp_path, payload):
    assert _scan(tmp_path, payload) == ["fixture.json: non-synthetic-username"]


@pytest.mark.parametrize(
    "payload",
    (
        {"kind": "t2", "data": {"name": "synthetic_user"}},
        {"fullname": "t2_account01", "name": "synthetic_user"},
        {"author_fullname": "t2_synthetic_user"},
        {"author_url": "https://www.reddit.com/user/synthetic_user/"},
        {"profile_url": "/u/synthetic_user/"},
        {"user_url": "https://old.reddit.com/user/synthetic_user/"},
    ),
)
def test_accepts_synthetic_reddit_user_identity_fields(tmp_path, payload):
    assert _scan(tmp_path, payload) == []


@pytest.mark.parametrize(
    "kind, fullname",
    (("t3", "t3_captured_post"), ("t5", "t5_captured_subreddit")),
)
def test_does_not_misclassify_non_user_thing_names(tmp_path, kind, fullname):
    payload = {"kind": kind, "data": {"name": fullname}}

    assert _scan(tmp_path, payload) == []
