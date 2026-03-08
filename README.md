# LLMWatch

**LLMOps SaaS Platform -- AI Observability & Orchestration**

LLMWatch is a full-stack LLMOps platform for monitoring, orchestrating, and securing Large Language Model deployments. It provides a unified API gateway for multi-model routing, autonomous AI agent orchestration with full execution tracing, real-time cost and latency analytics, and enterprise API key management with per-key usage tracking.

## Live Demo

- **App:** http://3.236.50.182:3000
- **API:** http://3.236.50.182:3000/api

## Features

- **Multi-Model LLM Gateway** -- Route requests to multiple models (Gemini 3 Flash, Qwen via vLLM, any OpenAI-compatible endpoint) through a single API. Strategy pattern enables zero-downtime model swaps.
- **Autonomous AI Agents** -- LangChain ReAct agent with 4 tools (web search, code execution, DB query, document analysis) and real-time step-by-step execution streaming via SSE.
- **Real-Time Analytics Dashboard** -- Track cost, latency, request volume, and error rates across all models with live-updating charts.
- **Agent Trace Viewer** -- Full execution trace storage in DynamoDB with timeline visualization, tool usage breakdown, and per-step latency metrics.
- **API Key Management** -- Create, list, regenerate, and revoke API keys for programmatic access. Per-key usage tracking (request count, last used). Keys are SHA-256 hashed at rest.
- **Dual Authentication** -- All protected endpoints accept either JWT Bearer token (browser login) or `X-API-Key` header (programmatic access).
- **MLFlow Integration** -- Every LLM call is logged to MLFlow for experiment tracking, model comparison, and metric aggregation.
- **Multi-Tenant Security** -- JWT authentication with company-scoped data isolation. All DynamoDB queries are partitioned by `company_id`.
- **Reasoning Mode** -- Enable deep thinking mode to see the LLM's chain-of-thought reasoning traces alongside responses.
- **Export & Search** -- Filter and search raw invocation logs, export to CSV.

## Architecture

```
┌──────────────────────┐
│   React 19 SPA       │  TypeScript, Vite 6, Tailwind v4
│   (Nginx :3000)      │  React Router v7, Zustand, Framer Motion
└──────────┬───────────┘
           │ JWT / X-API-Key / REST API
┌──────────▼───────────┐
│   FastAPI Server     │  Python 3.11, Pydantic v2
│   (Uvicorn :8000)    │  LangChain, slowapi, JWT + API Key auth
└──────────┬───────────┘
           │
     ┌─────┼──────────┬────────────────┐
     │     │          │                │
┌────▼──┐ ┌▼───────┐ ┌▼────────────┐ ┌▼──────────┐
│ Qwen  │ │Gemini  │ │ DynamoDB    │ │  MLFlow   │
│(vLLM) │ │(Google)│ │ (4 tables)  │ │ (Docker)  │
│ opt.  │ │        │ │             │ │           │
└───────┘ └────────┘ └─────────────┘ └───────────┘
```

### Backend Services

| Service | Purpose |
|---|---|
| `LLMService` | Strategy-based model routing (Gemini/Qwen) |
| `AgentService` | ReAct agent orchestration with async SSE streaming |
| `TracingService` | LangChain callback handler for step capture |
| `DynamoDBService` | Multi-tenant data access (logs, users, traces, API keys) |
| `MLFlowService` | Async experiment logging and metric tracking |

### Agent Tools

| Tool | Description |
|---|---|
| `web_search` | DuckDuckGo search (no API key required) |
| `code_execute` | Sandboxed Python execution via subprocess |
| `db_query` | Query your own LLM usage logs (company-scoped) |
| `doc_analyze` | Fetch and extract text from any URL |

### DynamoDB Tables

| Table | PK | SK / GSI | Purpose |
|---|---|---|---|
| `llmwatch_logs` | `company_id` | `timestamp#log_id` | LLM call logs |
| `llmwatch_users` | `company_id` | `user_id` | User accounts |
| `llmwatch_traces` | `company_id` | `run_ts#run_id` | Agent execution traces |
| `llmwatch_api_keys` | `key_hash` | GSI: `company_id-index`, `key_id-index` | API key auth & management |

## Programmatic Access (API Keys)

API keys enable programmatic access without browser login. Create a key from the Settings page, then use the `X-API-Key` header with any endpoint.

### Chat Completion
```bash
curl http://YOUR_HOST:3000/api/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: lw_YOUR_KEY_HERE" \
  -d '{"prompt":"Explain quantum computing","model":"gemini","thinking_mode":false}'
```

### Run an Agent
```bash
curl http://YOUR_HOST:3000/api/agent/run \
  -H "Content-Type: application/json" \
  -H "X-API-Key: lw_YOUR_KEY_HERE" \
  -d '{"prompt":"Search the web for latest AI news","model":"gemini","tools":["web_search"],"max_iterations":5}'
```

### Get Analytics
```bash
curl http://YOUR_HOST:3000/api/analytics/summary \
  -H "X-API-Key: lw_YOUR_KEY_HERE"
```

### List API Keys
```bash
curl http://YOUR_HOST:3000/api/api-keys \
  -H "X-API-Key: lw_YOUR_KEY_HERE"
```

## Tech Stack

### Backend
- Python 3.11 / FastAPI / Uvicorn
- LangChain 0.3.x (ReAct agent + model routing)
- Pydantic v2 (validation + settings)
- boto3 (DynamoDB)
- MLFlow 3.x
- python-jose (JWT)
- slowapi (rate limiting)
- duckduckgo-search (agent web search)

### Frontend
- React 19 / TypeScript 5
- Vite 6 (build tooling)
- React Router v7 (data API routing)
- Tailwind CSS v4
- Zustand (state management)
- Framer Motion (animations)
- Recharts (data visualization)
- Radix UI (accessible primitives)
- Lucide React (icons)

### Infrastructure
- Docker Compose (3 services: backend, frontend, MLFlow)
- Nginx (frontend reverse proxy + SPA routing + API proxy)
- AWS EC2 (production deployment)
- AWS DynamoDB (4 tables, PAY_PER_REQUEST)
- GitHub Actions (CI/CD auto-deploy on push to main)

## Project Structure

```
llmwatch/
├── backend/
│   ├── auth/              # JWT handler + dual auth (JWT + API key)
│   ├── middleware/         # CORS, security headers
│   ├── models/            # Pydantic schemas
│   ├── routers/           # FastAPI route handlers
│   │   ├── agent.py       # SSE streaming + trace endpoints
│   │   ├── analytics.py   # Metrics + log queries
│   │   ├── api_keys.py    # API key CRUD (create/list/regenerate/revoke)
│   │   ├── auth.py        # Login/register
│   │   └── chat.py        # LLM completions
│   ├── scripts/           # DB setup utilities
│   │   └── create_api_keys_table.py
│   ├── services/          # Business logic layer
│   │   ├── agent_service.py    # ReAct agent orchestration
│   │   ├── dynamo_service.py   # DynamoDB CRUD (logs, users, traces, API keys)
│   │   ├── llm_service.py      # Model strategy routing
│   │   ├── mlflow_service.py   # Experiment tracking
│   │   └── tracing_service.py  # Callback handler + events
│   ├── tests/             # pytest suite (144+ tests)
│   ├── tools/             # LangChain agent tools
│   │   ├── web_search.py
│   │   ├── code_executor.py
│   │   ├── db_query.py
│   │   └── doc_analyzer.py
│   ├── config.py          # Pydantic settings
│   ├── exceptions.py      # Custom exception hierarchy
│   ├── main.py            # FastAPI app entry point
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/           # Axios client, agent API, settings API
│   │   ├── components/
│   │   │   ├── agent/     # AgentStepCard, Timeline, ToolConfig, SummaryCard
│   │   │   ├── Dashboard/ # MetricCard
│   │   │   └── Layout/    # Sidebar, Navbar
│   │   ├── hooks/         # useAgentStream (POST + SSE)
│   │   ├── routes/        # Page components (dashboard, chat, agent, settings)
│   │   ├── store/         # Zustand store
│   │   └── types/         # TypeScript interfaces
│   ├── nginx.conf
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
├── .github/workflows/
│   └── deploy.yml         # CI/CD: auto-deploy to EC2 on push to main
├── docker-compose.yml
├── .env.example
└── README.md
```

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Node.js 22+ (for local frontend development)
- Python 3.11+ (for local backend development)
- AWS credentials (for DynamoDB)
- Google API key (for Gemini)

### Environment Setup

```bash
# Clone the repository
git clone https://github.com/omer-ulucan/llmwatch.git
cd llmwatch

# Copy environment template
cp .env.example backend/.env
# Edit backend/.env with your actual values (API keys, JWT secret, AWS creds)
```

### Run with Docker Compose

```bash
docker compose up --build
```

This starts three services:
- **Frontend** (Nginx): http://localhost:3000
- **Backend** (FastAPI): http://localhost:8000
- **MLFlow**: http://localhost:5000

### Local Development

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

**Tests:**
```bash
cd backend
source venv/bin/activate
pytest -v
```

## API Endpoints

### Authentication
| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/register` | None | Create account |
| `POST` | `/auth/login` | None | Get JWT token |

### Chat
| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/chat/completions` | JWT or API Key | LLM inference with model routing |

### Agent
| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/agent/run` | JWT or API Key | Execute agent (SSE stream) |
| `GET` | `/agent/traces` | JWT or API Key | List recent traces |
| `GET` | `/agent/traces/{run_id}` | JWT or API Key | Full trace detail |
| `GET` | `/agent/analytics` | JWT or API Key | Agent aggregate metrics |

### Analytics
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/analytics/summary` | JWT or API Key | Aggregate KPIs |
| `GET` | `/analytics/timeseries` | JWT or API Key | Time-series metrics |
| `GET` | `/analytics/logs` | JWT or API Key | Raw invocation logs |

### API Keys
| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api-keys` | JWT or API Key | Create new API key (raw key returned once) |
| `GET` | `/api-keys` | JWT or API Key | List all keys (masked) |
| `POST` | `/api-keys/{key_id}/regenerate` | JWT or API Key | Rotate key (revoke old, issue new) |
| `DELETE` | `/api-keys/{key_id}` | JWT or API Key | Permanently revoke key |

## Environment Variables

See [`.env.example`](.env.example) for the full list:

| Variable | Description | Required |
|---|---|---|
| `AWS_REGION` | AWS region for DynamoDB | Yes |
| `AWS_ACCESS_KEY_ID` | AWS credentials | Yes |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials | Yes |
| `DYNAMODB_TABLE_LOGS` | Logs table name | Yes |
| `DYNAMODB_TABLE_USERS` | Users table name | Yes |
| `DYNAMODB_TABLE_TRACES` | Agent traces table name | Yes |
| `DYNAMODB_TABLE_API_KEYS` | API keys table name | Yes |
| `JWT_SECRET_KEY` | Secret for JWT signing (min 32 chars) | Yes |
| `GOOGLE_API_KEY` | Google Gemini API key | Yes |
| `QWEN_BASE_URL` | vLLM endpoint for Qwen (optional) | No |
| `QWEN_API_KEY` | Qwen API key (optional) | No |
| `MLFLOW_TRACKING_URI` | MLFlow server URL | Yes |
| `CORS_ORIGINS` | Allowed CORS origins | Yes |

## How LLMWatch Compares

| Capability | LLMWatch | LangSmith | Helicone | Arize AI | Weights & Biases |
|---|:---:|:---:|:---:|:---:|:---:|
| **LLM Gateway / Routing** | Yes | No | Proxy only | No | No |
| **AI Agent Orchestration** | Yes (ReAct + tools) | No | No | No | No |
| **Agent Execution Tracing** | Yes (step-level SSE) | Yes | No | No | No |
| **Observability Dashboard** | Yes | Yes | Yes | Yes | Yes |
| **Cost & Latency Tracking** | Yes | Yes | Yes | Yes | Partial |
| **API Key Management** | Yes (per-key usage) | Yes | Yes | No | No |
| **Dual Auth (JWT + API Key)** | Yes | No | No | No | No |
| **Multi-Model Support** | Yes (Gemini, Qwen, OpenAI-compat) | LangChain models | OpenAI-compat | Any | Any |
| **Self-Hostable** | Yes (Docker Compose) | No (cloud only) | Yes | No | No |
| **Open Source** | Yes | Partial | Yes | No | No |
| **MLFlow Integration** | Yes (built-in) | No | No | No | No |
| **Multi-Tenant Isolation** | Yes (company-scoped) | Yes | Yes | Yes | Yes |
| **Real-Time Streaming** | Yes (SSE) | Yes | No | No | No |

### Key Differentiators

- **All-in-one platform:** LLMWatch combines LLM routing, agent orchestration, observability, and API management in a single self-hosted solution. Competitors typically cover only one or two of these.
- **Agent-first design:** Built-in ReAct agent with 4 tools and full execution tracing -- not just passive monitoring but active orchestration.
- **Self-hosted & open:** Deploy on your own infrastructure with Docker Compose. No vendor lock-in, no data leaving your network.
- **Enterprise API keys:** SHA-256 hashed keys with per-key usage tracking, rotation, and revocation -- same security model as Stripe and OpenAI.

## License

Private -- All rights reserved.
