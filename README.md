# LLMWatch

**Self-hosted LLM observability and evals.** Log every model call with tokens, latency and cost, trace agent runs step by step, and compare models and prompts with evals that tell you whether a difference is real or noise.

- **Evals with honest statistics.** Write test suites in YAML and run them against several models at once. Comparisons report a paired-bootstrap confidence interval for the score and McNemar's test for pass/fail. With too few cases they say so instead of declaring a winner.
- **Cost as a first-class axis.** Every call records the token usage the provider reports and the cost from your model prices. Eval runs plot quality against cost per case.
- **Any OpenAI-compatible provider.** OpenAI, Gemini, OpenRouter, Groq, Together, or local Ollama, vLLM and LM Studio. Keys are encrypted at rest and never returned by the API.
- **Chat playground and a traced agent.** Responses stream with reasoning shown separately. The agent's tool calls appear live, and every run is saved as a trace with per-step latency and cost.
- **Analytics.** Requests, errors, p50/p95 latency and spend over any window, compared with the previous one. Filterable call log with CSV export.
- **Evals in CI.** The `llmwatch` CLI exits non-zero only on a *significant* regression against a baseline run.
- **Zero-config deployment.** `docker compose up` gives you the API and UI on one port, with SQLite on a named volume. Postgres is optional.

<!-- TODO(screenshots): add docs/screenshots/{dashboard,evals-compare,agent-trace}.png -->
| Dashboard | Eval comparison | Agent trace |
|---|---|---|
| _screenshot placeholder_ | _screenshot placeholder_ | _screenshot placeholder_ |

## Quickstart (60 seconds)

```bash
git clone https://github.com/omer-ulucan/llmwatch.git
cd llmwatch
docker compose up -d
```

Open <http://localhost:3000> and create an account. The first boot generates a secret key and stores it in the `llmwatch_data` volume. Then:

1. Open **Models**, pick a provider preset, paste a key (or point it at Ollama, see below), and click **Discover**.
2. Set per-million-token prices on the models you want cost for. LLMWatch ships no price list, so unpriced models are shown as *unpriced*, not $0.
3. Try **Chat**, run the **Agent**, or open **Evals** and create a suite from the starter template.

Once your account exists, you can set `ALLOW_SIGNUP=false` to close registration.

## Providers

Providers are managed per workspace in the UI. A provider can also be seeded into every workspace from the environment: put the variables in a `.env` file next to `docker-compose.yml`.

| Provider | Environment variable | Notes |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | |
| Google Gemini | `GOOGLE_API_KEY` | Uses Gemini's OpenAI-compatible endpoint |
| OpenRouter | `OPENROUTER_API_KEY` | |
| Groq | `GROQ_API_KEY` | |
| Together | `TOGETHER_API_KEY` | |
| Ollama | `OLLAMA_BASE_URL` | e.g. `http://localhost:11434/v1` |
| vLLM | `VLLM_BASE_URL`, `VLLM_API_KEY` | Any vLLM OpenAI server |
| LM Studio, others | UI only (preset or *Custom*) | Any OpenAI-compatible base URL |

### Ollama

Running the backend directly on the host:

```bash
OLLAMA_BASE_URL=http://localhost:11434/v1
```

Running LLMWatch with Docker Compose and Ollama on the host: Ollama only listens on loopback by default, which containers cannot reach. Make it listen on all interfaces, then use the host gateway that the compose file maps:

```bash
# on the host (for the systemd service, set it with: systemctl edit ollama)
OLLAMA_HOST=0.0.0.0 ollama serve
```

```bash
# .env next to docker-compose.yml
OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
```

Reasoning models (Qwen 3, DeepSeek R1, …) are told not to think unless you turn thinking on. Otherwise a short answer can be lost to hidden reasoning.

### Model references

Anywhere a model is expected (chat, agent, eval variants, the CLI) you can pass the model's id, `Provider/model-id` (for example `Ollama/qwen3:8b`), or `default` (the workspace's default model).

## Evals

A suite is a prompt template, cases that fill its `{{ variables }}`, and assertions:

```yaml
name: capitals
system_prompt: You are a concise assistant.
prompt: |
  Answer with one word: what is the capital of {{ country }}?
assert:                     # applies to every case
  - {type: not_contains, value: "I'm not sure"}
cases:
  - id: france
    vars: {country: France}
    assert:
      - {type: contains, value: Paris, case_sensitive: false}
  - id: japan
    vars: {country: Japan}
    assert:
      - {type: contains, value: Tokyo, case_sensitive: false}
      - {type: latency_under, value: 5000, weight: 0.5}
```

A bigger example with JSON output, a schema check, regexes and an LLM judge is in [`examples/support-triage.yaml`](examples/support-triage.yaml).

**Evaluators:** `exact_match`, `contains`, `not_contains`, `regex`, `json_valid`, `json_schema`, `similarity` (embeddings), `llm_judge` (rubric, JSON score and reasoning, temperature 0; it warns when the judge and the candidate share a model family), `latency_under`, `cost_under`. Each returns a score in [0, 1], pass/fail and a reason. A case's score is the weighted mean of its assertions, and it passes only when every assertion passes.

**Versions.** Editing a suite saves a new immutable version, and runs keep pointing at the version they ran.

**Runs.** One run per *variant*: a model plus temperature, max tokens and thinking. Repeats measure flakiness. Runs execute in the background with bounded concurrency, a per-provider rate limit, and retries with jittered backoff that honor `Retry-After`. Responses are cached by model, parameters, messages and repeat number, so re-running an unchanged variant makes no provider calls. Cancelled runs, and runs interrupted by a restart, can be resumed.

**Comparisons.** Results are paired by case and repeat:

- mean score delta with a 95% paired-bootstrap confidence interval (10,000 resamples, fixed seed),
- pass-rate change with McNemar's test (exact binomial below 25 discordant pairs, χ² with continuity correction above),
- cost-per-case and latency deltas,
- per-case regressions and fixes.

The verdict stays "no significant difference" unless a test finds one. Below 10 paired cases the interval is not used for significance, and the comparison carries a warning. It also warns about different suite versions and unpriced models.

## CLI

The `llmwatch` command is installed with the backend package. It runs suites against the local database (the same one the server uses) or against a running server.

```bash
# local: uses DATABASE_URL; pass --workspace if there are several workspaces
llmwatch eval run examples/support-triage.yaml --model Ollama/qwen3:8b \
  --param temperature=0 --set-baseline

# CI: against a server with an API key, fail only on a significant regression
llmwatch eval run examples/support-triage.yaml --model OpenAI/gpt-4o-mini \
  --server https://llmwatch.example.com --api-key "$LLMWATCH_API_KEY" \
  --baseline suite --fail-on-regression --json

llmwatch eval compare <baseline-run-id> <candidate-run-id>
```

`--baseline` takes a run id, or `suite` for the suite's baseline run (`--set-baseline` marks the new run as baseline if nothing regressed). Other options: `--repeats`, `--concurrency`, `--judge-model`, `--embedding-model`, `--thinking`, `--no-cache`, `--param max_tokens=…`.

| Exit code | Meaning |
|---|---|
| 0 | Finished; with `--fail-on-regression`, no significant regression |
| 1 | Significant regression (only with `--fail-on-regression`) |
| 2 | Usage, configuration or run error |

## Configuration

Everything is optional. Settings are environment variables, or a `.env` file. [`.env.example`](.env.example) documents every one. The ones you are most likely to touch:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | SQLite in `./data` (`/data` in Docker) | Or `postgresql+asyncpg://user:pass@host/db` (install the `postgres` extra) |
| `SECRET_KEY` | generated into `SECRET_KEY_FILE` | ≥ 32 chars if set. JWT and provider-key encryption keys derive from it, so back it up |
| `ALLOW_SIGNUP` | `true` | `false`: only the first account can register |
| `ENABLE_CODE_EXECUTION` | `false` | Registers the agent's `python` tool (see Security) |
| `FETCH_ALLOWED_HOSTS` | | Hosts `fetch_url` may reach even though they resolve to private IPs |
| `TRUSTED_PROXIES` | | CIDRs whose `X-Forwarded-For` is trusted (compose sets the Docker networks) |
| `RATE_LIMIT_CHAT` / `RATE_LIMIT_AGENT` | `60/minute` / `10/minute` | Per user or API key |
| `PROVIDER_ALLOW_PRIVATE_URLS` | `true` | Set `false` on shared servers so workspace owners cannot point providers at the internal network |
| `EVAL_PROVIDER_CONCURRENCY` / `EVAL_PROVIDER_RPM` | `8` / `600` | Per-provider limits across all eval runs |
| `MLFLOW_TRACKING_URI` | | Also log calls to MLflow (needs the `mlflow` extra) |

## Architecture

```mermaid
flowchart LR
  browser[Browser: React SPA] -->|/api, SSE| nginx[nginx]
  cli[llmwatch CLI] -->|X-API-Key| api
  cli -. local mode .-> db
  nginx --> api[FastAPI]
  api --> db[(SQLite or Postgres)]
  api --> runner[Eval runner: background tasks]
  runner --> db
  api -->|OpenAI-compatible HTTP| providers[OpenAI, Gemini, OpenRouter, Groq, Together, Ollama, vLLM, LM Studio]
  runner --> providers
  api -. optional .-> mlflow[MLflow]
```

- **Backend** (`backend/src/llmwatch`): FastAPI with async SQLAlchemy 2 and Alembic migrations, which run on startup. Modules: `llm/` (OpenAI-compatible client, streaming, usage, reasoning controls), `providers/` (registry, presets, encrypted keys), `agent/` (tool-calling loop, tools, SSE events), `evals/` (suites, evaluators, runner, statistics, CLI), `security/` (SSRF guard), `routers/` (HTTP API).
- **Frontend** (`frontend/src`): React 19, Vite, Tailwind v4, TanStack Query and Recharts, with lazy-loaded routes.
- **Data**: one database. Every table is scoped by workspace, and the repositories enforce that scope.

More detail is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Security notes

- **Workspace isolation.** All queries go through workspace-scoped repositories. Tests check that one workspace cannot read or change another's data.
- **Provider keys** are encrypted with a key derived from `SECRET_KEY` and only ever returned masked. If you lose the secret, stored keys become unreadable and everyone is logged out.
- **Code execution is off by default.** With `ENABLE_CODE_EXECUTION=true`, the agent's `python` tool runs model-written code in a child process: isolated mode, empty environment, temporary working directory, CPU/memory/file limits and a timeout. **It is not a sandbox.** The code runs as the backend user, on the same filesystem and network. Only enable it where that is acceptable.
- **SSRF.** `fetch_url` resolves the host and refuses private, loopback, link-local, multicast, reserved and cloud metadata addresses (IPv4 and IPv6, including IPv4-mapped forms). It re-checks every redirect and connects to the vetted IP, which defeats DNS rebinding. `FETCH_ALLOWED_HOSTS` exempts specific hosts.
- **Rate limits and proxies.** Limits apply per API key, per user and per IP. `X-Forwarded-For` is only honored from `TRUSTED_PROXIES`, and the bundled nginx overwrites it rather than appending.
- **Demo mode** (`DEMO_MODE=true`) seeds a public demo login and the example suite. The server refuses to start with it when `APP_ENV=production`.
- No telemetry is sent anywhere.

## Development

```bash
# backend (Python 3.11+)
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn llmwatch.main:app --reload        # http://localhost:8000, OpenAPI at /docs

# frontend (Node 20+)
cd frontend && npm install
npm run dev                               # http://localhost:3000, proxies /api to :8000
```

Checks (CI runs the same, plus the suite on Postgres and a Docker smoke test):

```bash
cd backend && ruff check . && ruff format --check . && pytest
cd frontend && npm run lint && npx tsc -b && npm run build && npm test
```

Tests never touch the network: a fake OpenAI-compatible provider stands in for real models, and the suite fails any non-loopback connection. See [CONTRIBUTING.md](CONTRIBUTING.md) for branch and commit conventions.

## Performance

TODO(measure): logging overhead per call, eval throughput against a local model, and memory use of the backend container. No numbers are published until they have been measured.

## License

[MIT](LICENSE)
