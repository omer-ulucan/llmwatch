# Contributing to LLMWatch

Thanks for helping. This guide covers setup, the checks every change must pass, and how branches and commits are organised.

## Setup

Requirements: Python 3.11+, Node 20+, and optionally Docker and a local Ollama for trying real models.

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # add ",postgres" to run the suite against Postgres
uvicorn llmwatch.main:app --reload # http://localhost:8000 (OpenAPI docs at /docs)

# frontend
cd frontend
npm install
npm run dev                        # http://localhost:3000, proxies /api to :8000
```

Configuration is optional. See [`.env.example`](.env.example) for every variable. For local models, `OLLAMA_BASE_URL=http://localhost:11434/v1` in `backend/.env` is enough.

## Checks

Run all of these before opening a pull request. CI runs the same, plus the suite on Postgres and a Docker Compose smoke test.

```bash
cd backend
ruff check .
ruff format --check .
pytest                            # add --cov for a coverage report

cd frontend
npm run lint
npx tsc -b
npm run build
npm test
```

To run the backend suite against Postgres, point `TEST_DATABASE_URL` at an empty database:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/llmwatch_test pytest
```

## Tests

- **Every fix comes with a regression test that fails before the fix.** Say in the commit message how you saw it fail.
- **Every feature ships with tests.**
- **Never skip, delete or weaken a test to get green.** If a test is genuinely obsolete, remove it and explain why in the commit message.
- **No network.** Use `tests/fake_llm.py` (a fake OpenAI-compatible provider), `httpx.MockTransport`, or stub resolvers. An autouse fixture fails any test that connects beyond loopback.
- **Database tests** use the `db_engine` / `db_session` fixtures (a fresh SQLite file per test, or `TEST_DATABASE_URL`). Schema changes need an Alembic migration in `backend/src/llmwatch/db/migrations/versions/`. `test_migrations_match_the_models` fails if models and migrations drift.
- **Frontend unit tests** (vitest) live next to the code as `*.test.ts`.

## Branches and commits

- **Never commit to `main` directly.** Branch from an up-to-date `main`, and name the branch by type:
  - `fix/<short-name>`: bug fixes
  - `feat/<short-name>`: features
  - `chore/<short-name>`: tooling, CI, dependencies, cleanup
  - `docs/<short-name>`: documentation
- **Keep branches small and focused.** Split big work into several branches merged in order.
- **Use [Conventional Commits](https://www.conventionalcommits.org/)** (`feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`), with a scope where it helps (`fix(evals): …`). The body says what changed and why.
- **Merges into `main` use `git merge --no-ff`**, so each branch stays visible in history. The checks must pass on the branch, and again on `main` after the merge.

## Code style

- **Python:** ruff for lint and format (config in `backend/pyproject.toml`), type hints on public functions, and async all the way down to the database and HTTP clients.
- **TypeScript:** strict mode, and no `any` in new code. Server state goes through TanStack Query, and UI primitives come from `components/ui`.
- **Comments** explain *why*, not what. Module docstrings carry a short `WHY:` where the design is not obvious.
- **Never invent numbers.** That covers benchmarks, savings, usage statistics and trends, in the UI, docs or README. If something needs a measurement, leave a `TODO(measure)` until someone measures it. `public-claims.test.ts` guards the public pages and the README.

## Security issues

Please report vulnerabilities privately through GitHub's security advisories for this repository rather than in a public issue.
