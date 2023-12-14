# Contributing

Thank you for helping improve Verity. Please keep changes explainable, privacy-preserving, and honest about uncertainty.

## Development setup

Follow the local setup in [README.md](README.md), then install the backend development dependencies from `backend/requirements-dev.txt` and the frontend dependencies with `npm ci` in `frontend/`.

## Before opening a pull request

Run from the repository root or the indicated working directory:

```bash
cd backend
../.venv/bin/ruff check app tests
../.venv/bin/mypy app
../.venv/bin/pytest --cov=app --cov-report=term-missing
cd ..
python scripts/evaluate.py
cd frontend
npm run build
npm run test:e2e
npm audit --audit-level=high
```

On Windows, use the virtual-environment executable at `..\.venv\Scripts\python.exe` or activate the environment and use `python -m ...`.

Add deterministic tests for behavior changes. The hand-authored fixture evaluator is a local regression aid, not a benchmark; do not describe its score as real-world fact-checking accuracy. Do not add fabricated quotations, sources, confidence values, or evaluation results.

## Data and security

- Never commit real documents, user text, databases, provider credentials, `.env` files, or test artifacts.
- Use synthetic fixtures and fake provider responses in tests. Tests must not make paid-provider calls or uncontrolled web requests.
- Preserve SSRF defenses, upload bounds, secret redaction, HTML escaping, owner scoping, explicit cloud-processing consent, and the distinction between source support and objective truth.
- Treat webpages, uploaded files, and model responses as untrusted input. Do not add browser-side execution of retrieved content.
- Document new environment variables, migrations, provider behavior, and platform-specific limitations.

## Pull request expectations

Keep the change focused, explain the user impact and limitations, include test output, and update the README or screenshots when user-visible behavior changes. Do not claim Linux, Windows, or Docker verification unless it actually ran.
