# Contributing

## Development setup

Use Python 3.11 or later. Install the package and development tools:

```bash
python -m pip install -e ".[dev]"
```

Keep changes focused, use English for code and documentation, and preserve the read-only, anonymous design. Do not add login, credential handling, writes, batch crawling, or browser-evasion mechanisms.

## Offline checks

CI is offline and must not launch a browser or contact Reddit. Run the same checks before submitting a change:

```bash
ruff check .
ruff format --check .
python scripts/check_fixtures_pii.py
pytest
```

Do not suppress warnings or weaken tests to make a change pass. Browser/live checks are opt-in and must not be added to the normal CI path.

## Tests and fixtures

Tests must be fixture-driven, deterministic, and browser-free. Use hand-authored synthetic JSON only. Never commit real Reddit captures, output files, browser profiles, cookies, credentials, or personally identifying data.

Fixtures must use synthetic usernames and identifiers. The fixture PII scanner is a safeguard, not permission to include real data. Store temporary captures only outside version control and delete them when they are no longer needed.

## Privacy and diagnostics

Treat Reddit results as third-party personal data, even when publicly visible. Diagnostic surfaces must redact sensitive data. Structured command output is deliberately not redacted, so contributors must keep it out of the repository and share it only when necessary and appropriately sanitized.

## Pull requests

Describe the behavior changed, the relevant offline checks run, and any user-visible CLI or schema change. Update directly affected tests and documentation. Do not include generated output or real Reddit data in a pull request.

By contributing, you agree that contributions are made under the repository's [MIT License](LICENSE).
