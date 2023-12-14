# AI Hallucination & Citation Verification Assistant

Checks AI answers against cited evidence and flags unsupported or hallucinated claims.

## Features

- Extracts atomic claims and preserves character offsets in AI-generated text.
- Associates citations, URLs, DOIs, footnotes, and reference-list entries with claims.
- Retrieves public pages and PDFs or accepts pasted evidence, recording hashes and page offsets.
- Classifies outcomes as supported, partially supported, contradicted, insufficient evidence, missing, unavailable, or needs review.
- Supports background analyses, batches, revision comparison, and human review history.
- Exports JSON, CSV, Markdown, and HTML and exposes a FastAPI/OpenAPI interface.

## Stack

Python, Node.js, FastAPI, Uvicorn, SQLAlchemy, HTTPX, React, Vite, TypeScript, Docker

## Clone

```bash
git clone https://github.com/sanjaymouraly/ai-hallucination-citation-verifier.git
cd ai-hallucination-citation-verifier
```

## Setup

```bash
# The project ships a Docker Compose setup.
docker compose up --build
```

See `docs/` or the compose file for environment variables and ports.

## Run

```bash
docker compose up --build
```

## Tests

```bash
pytest -q
```

## Notes

- Sample data, when included, is synthetic.

## License

MIT © 2023 [Sanjay Mouraly](https://github.com/sanjaymouraly)
