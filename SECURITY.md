# Security policy

## Supported use and threat model

Verity is designed first for a **single-user, local installation**. The API has optional bearer-token owner isolation, but it is not an identity provider: there is no MFA, federated sign-in, per-user rate limiting, or administrator console. With `APP_API_TOKENS` unset, the API is intentionally unauthenticated and must remain bound to loopback or behind a trusted local-only boundary. Do not expose that configuration to a network.

For a shared or remotely reachable deployment, configure unique high-entropy tokens, use HTTPS through a trusted reverse proxy, keep the database and encryption key private, restrict network egress, and review provider endpoints. The included Compose file binds the web UI to `127.0.0.1` by default.

## Implemented safeguards

- Public-source retrieval accepts HTTP(S) on standard ports only, rejects non-public DNS/IP results, pins the validated addresses for the socket connection while retaining the original hostname for TLS verification/SNI, and revalidates every redirect.
- Public-source requests do not forward environment proxy settings, cookies, or credentials; redirects are followed manually, with bounded counts, response bytes, timeouts, and extracted text.
- Upload types and sizes are bounded; PDF page count and DOCX archive expansion are capped. Uploaded documents are parsed as data, never executed. Scanned PDFs require separate OCR.
- Provider output is schema-checked and status-limited. Source text is labelled untrusted in optional assessment prompts; treat that as a mitigation, not a guarantee against prompt injection.
- Provider credentials are not returned by the API or written to application logs. Without `APP_ENCRYPTION_KEY`, a key entered in the UI is held in process memory only; with a valid Fernet key it is encrypted in the database. Environment variables take precedence.
- Exported HTML escapes user-controlled text. API responses include basic anti-sniffing, frame, and referrer headers. The production Nginx configuration adds a restrictive Content Security Policy.
- Owner-scoped queries isolate records when `APP_API_TOKENS` is configured.

## Reporting a vulnerability

Please do not publish exploit details, private source material, API keys, or personally identifying data in a public issue. Use the repository host's private vulnerability-reporting feature when available. If that feature is unavailable, open a minimal public issue asking for a private contact channel without including exploit details.

Security reports should include the affected version/commit, a concise impact description, and minimal reproducible steps. Do not use real credentials or real customer data in reproduction steps.
