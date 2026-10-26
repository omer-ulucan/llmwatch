# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

A rewrite into a self-hostable platform. Upgrading from 1.0.0 is not supported:
data lived in DynamoDB, which is gone.

### Added
- **Database:** SQLAlchemy 2 (async) on SQLite by default or Postgres, with Alembic migrations applied on startup and workspace-scoped repositories.
- **Zero-config deployment:** `docker compose up` with a named volume. The secret key is generated on first boot, the backend image runs as non-root, and nginx is configured for SSE.
- **Provider and model registry:** presets for OpenAI, Gemini, OpenRouter, Groq, Together, Ollama, vLLM and LM Studio; encrypted, masked keys; connection test and model discovery; per-model prices and capabilities; seeding from environment variables.
- **Chat:** completions and SSE streaming against any registered model, with reasoning separated from the answer, provider-reported token usage and cost. Every call is logged, including failures.
- **Agent:** a native async tool-calling loop (`web_search`, `fetch_url`, `query_usage`, opt-in `python`) with live SSE events, cancellation and full traces.
- **Evals:** YAML/JSON suites with immutable versions; ten evaluators (exact match, contains, regex, JSON, JSON schema, similarity, LLM judge, latency, cost); a background runner with concurrency limits, per-provider throttling, retries honoring `Retry-After`, a response cache and resume; comparisons with paired-bootstrap intervals and McNemar's test; suite baselines.
- **CLI:** `llmwatch eval run` / `llmwatch eval compare`, locally or against a server, exiting 1 only on a significant regression.
- **UI:** models page, streaming chat with markdown, agent waterfall and trace detail, data-driven dashboard and analytics (time ranges, filters, search, CSV), API key dialogs, workspace deletion, and eval pages (suites, runs, comparisons, quality vs cost).
- **CI:** lint, format, tests with coverage, the suite on Postgres, a frontend build with unit tests, and a Docker Compose smoke test.

### Changed
- Authentication uses PyJWT and SQL-backed users, workspaces and API keys. Registration creates a workspace and its owner, and can be closed with `ALLOW_SIGNUP=false`.
- Chat and agent requests take any model reference (`Provider/model`, a model id or `default`) instead of only `qwen` / `gemini`. The old aliases still work when those providers are configured.
- Agent tools were renamed (`code_execute` → `python`, `db_query` → `query_usage`, `doc_analyze` → `fetch_url`). The old names are accepted as aliases.
- Analytics are computed in SQL over a selectable window (`hours` or `from`/`to`), with zero-filled time buckets, p50/p95 latency, per-model breakdown and period-over-period changes.

### Removed
- DynamoDB, boto3 and all AWS configuration; LangChain; the deploy workflow that pruned Docker volumes.
- Fabricated content from the UI: compliance, uptime and savings claims, invented usage statistics, and trend badges that were not computed.

### Fixed
- Logs and traces were never persisted (DynamoDB rejected float values, and errors were swallowed in background threads).
- Agent traces were saved empty and agent costs were always $0.
- Failed model calls were not logged, so error rates read 0%.
- The analytics `hours` parameter was ignored.
- The SSE parser dropped events split across network chunks.

### Security
- SSRF protection for URL fetching: private, loopback, link-local and metadata addresses are blocked (IPv4/IPv6), redirects are re-validated, and connections are pinned to the vetted IP.
- Code execution is off by default and resource-limited when enabled (documented as not a sandbox).
- Demo mode is off by default and refused in production; there are no shared hardcoded credentials.
- The secret key must be at least 32 characters; JWT and encryption keys are derived from it.
- Rate limits are keyed per API key, user and client IP. `X-Forwarded-For` is only trusted from `TRUSTED_PROXIES`.
- API key management requires a signed-in session (API keys cannot mint keys).
- `.env` files are excluded from Docker build contexts.

## [1.0.0] - 2026-03-07

### Added
- **Frontend**
  - Fully interactive awwwards-level user interface utilizing Glassmorphism.
  - Implemented React 19 concurrent routing with React Router v7 and Vite.
  - Complete Dark Mode theme mapped strictly in Tailwind CSS v4 variables.
  - Live cost tracking, request KPIs, and reasoning trace extraction dashboards.
  - JWT integration via secure memory-bound Zustand stores.
- **Backend**
  - High performance structural FastAPI environment.
  - Implemented secure JWT issue endpoints.
  - Strategy Pattern implementation orchestrating local `Qwen3.5` and `Gemini 3`.
  - Background logging architecture directly streaming metrics to DynamoDB and MLFlow independently.
  - Defensive security integrations targeting rate usage and HTTP header exploitation.
- **Infrastructure**
  - Production-ready Docker networks.
  - Nginx configuration optimized for single page application resolution.
  - Initial configuration `.env` structuring.

### Changed
- Refactored `chat` component structure providing inline reasoning execution dropdowns (a.k.a thinking mode).
- Centralized Axios client intercepts to intercept globally and re-route users during unauthorized exceptions.

### Security
- Injected strict Pydantic model configurations blocking arbitrary metadata injection during database requests.
- Integrated `bcrypt` encoding over legacy MD5 configurations.
