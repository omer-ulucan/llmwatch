# LLMWatch

**AI Observability & Orchestration Platform**

LLMWatch is a full-stack platform for monitoring, comparing, and orchestrating Large Language Model deployments. It provides real-time cost tracking, latency monitoring, model comparison (self-hosted vs. managed), and an autonomous ReAct agent with full execution tracing.

## Features

- **Multi-Model Routing** -- Switch between self-hosted Qwen (via vLLM) and Google Gemini with a single toggle. Strategy pattern enables zero-downtime model swaps.
- **Real-Time Analytics Dashboard** -- Track cost, latency, request volume, and error rates across all models with live-updating charts (Recharts).
- **Reasoning Mode** -- Enable deep thinking mode to see the LLM's chain-of-thought reasoning traces alongside responses.
- **Autonomous Agent** -- LangChain ReAct agent with 4 tools (web search, code execution, DB query, document analysis) and real-time step-by-step execution streaming via SSE.
- **Agent Trace Viewer** -- Full execution trace storage in DynamoDB with timeline visualization, tool usage breakdown, and per-step latency metrics.
- **MLFlow Integration** -- Every LLM call is logged to MLFlow for experiment tracking, model comparison, and metric aggregation.
- **Multi-Tenant Security** -- JWT authentication with company-scoped data isolation. All DynamoDB queries are partitioned by `company_id`.
- **Export & Search** -- Filter and search raw invocation logs, export to CSV.

## Architecture

```
┌──────────────────────┐
│   React 19 SPA       │  TypeScript, Vite 6, Tailwind v4
│   (Nginx :3000)      │  React Router v7, Zustand, Framer Motion
└──────────┬───────────┘
           │ JWT / REST API
┌──────────▼───────────┐
│   FastAPI Server     │  Python 3.11, Pydantic v2
│   (Uvicorn :8000)    │  LangChain, slowapi, JWT auth
└──────────┬───────────┘
           │
     ┌─────┼──────────┬────────────────┐
     │     │          │                │
┌────▼──┐ ┌▼───────┐ ┌▼────────────┐ ┌▼──────────┐
│ Qwen  │ │Gemini  │ │ DynamoDB    │ │  MLFlow   │
│(vLLM) │ │(Google)│ │ (3 tables)  │ │ (Docker)  │
└───────┘ └────────┘ └─────────────┘ └───────────┘
```

### Backend Services

| Service | Purpose |
|---|---|
| `LLMService` | Strategy-based model routing (Qwen/Gemini) |
| `AgentService` | ReAct agent orchestration with async SSE streaming |
| `TracingService` | LangChain callback handler for step capture |
| `DynamoDBService` | Multi-tenant data access (logs, users, traces) |
| `MLFlowService` | Async experiment logging and metric tracking |

### Agent Tools

| Tool | Description |
|---|---|
| `web_search` | DuckDuckGo search (no API key required) |
| `code_execute` | Sandboxed Python execution via subprocess |
| `db_query` | Query your own LLM usage logs (company-scoped) |
| `doc_analyze` | Fetch and extract text from any URL |

### DynamoDB Tables

| Table | PK | SK | Purpose |
|---|---|---|---|
| `llmwatch_logs` | `company_id` | `timestamp#log_id` | LLM call logs |
| `llmwatch_users` | `company_id` | `user_id` | User accounts |
| `llmwatch_traces` | `company_id` | `run_ts#run_id` | Agent execution traces |

## Tech Stack

### Backend
- Python 3.11 / FastAPI / Uvicorn
- LangChain (ReAct agent + model routing)
- Pydantic v2 (validation + settings)
- boto3 (DynamoDB)
- MLFlow 2.14+
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
- Docker Compose (3 services)
- Nginx (frontend reverse proxy + SPA routing)
- MLFlow (SQLite backend, local artifact storage)

## Project Structure

```
llmwatch/
├── backend/
│   ├── auth/              # JWT handler + auth dependencies
│   ├── middleware/         # CORS, security headers
│   ├── models/            # Pydantic schemas
│   ├── routers/           # FastAPI route handlers
│   │   ├── agent.py       # SSE streaming + trace endpoints
│   │   ├── analytics.py   # Metrics + log queries
│   │   ├── auth.py        # Login/register
│   │   └── chat.py        # LLM completions
│   ├── services/          # Business logic layer
│   │   ├── agent_service.py    # ReAct agent orchestration
│   │   ├── dynamo_service.py   # DynamoDB CRUD
│   │   ├── llm_service.py      # Model strategy routing
│   │   ├── mlflow_service.py   # Experiment tracking
│   │   └── tracing_service.py  # Callback handler + events
│   ├── tests/             # pytest suite (55+ tests)
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
│   │   ├── api/           # Axios client + agent API
│   │   ├── components/
│   │   │   ├── agent/     # AgentStepCard, Timeline, ToolConfig, SummaryCard
│   │   │   ├── Dashboard/ # MetricCard
│   │   │   └── Layout/    # Sidebar, Navbar
│   │   ├── hooks/         # useAgentStream (POST + SSE)
│   │   ├── routes/        # Page components
│   │   ├── store/         # Zustand store
│   │   └── types/         # TypeScript interfaces
│   ├── nginx.conf
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
├── docs/
│   ├── ARCHITECTURE.md
│   ├── CHANGELOG.md
│   └── epochs/            # Development phase planning
├── docker-compose.yml
├── .env.example
└── README.md
```

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Node.js 22+ (for local frontend development)
- Python 3.11+ (for local backend development)
- AWS credentials (for DynamoDB) or DynamoDB Local

### Environment Setup

```bash
# Clone the repository
git clone <repo-url>
cd llmwatch

# Copy environment template
cp .env.example .env
# Edit .env with your actual values (API keys, JWT secret, etc.)
```

### Run with Docker Compose

```bash
docker compose up --build
```

This starts three services:
- **Backend** (FastAPI): http://localhost:8000
- **Frontend** (Nginx): http://localhost:3000
- **MLFlow**: http://localhost:5000

### Local Development

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
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
| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/register` | Create account |
| `POST` | `/auth/login` | Get JWT token |

### Chat
| Method | Path | Description |
|---|---|---|
| `POST` | `/chat/completions` | LLM inference with model routing |

### Analytics
| Method | Path | Description |
|---|---|---|
| `GET` | `/analytics/summary` | Aggregate KPIs |
| `GET` | `/analytics/timeseries` | Time-series metrics |
| `GET` | `/analytics/logs` | Raw invocation logs |

### Agent
| Method | Path | Description |
|---|---|---|
| `POST` | `/agent/run` | Execute agent (SSE stream) |
| `GET` | `/agent/traces` | List recent traces |
| `GET` | `/agent/traces/{run_id}` | Full trace detail |
| `GET` | `/agent/analytics` | Agent aggregate metrics |

## Environment Variables

See [`.env.example`](.env.example) for the full list:

| Variable | Description | Required |
|---|---|---|
| `AWS_REGION` | AWS region for DynamoDB | Yes |
| `AWS_ACCESS_KEY_ID` | AWS credentials (optional with IAM roles) | No |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials (optional with IAM roles) | No |
| `DYNAMODB_TABLE_LOGS` | Logs table name | Yes |
| `DYNAMODB_TABLE_USERS` | Users table name | Yes |
| `DYNAMODB_TABLE_TRACES` | Agent traces table name | Yes |
| `JWT_SECRET_KEY` | Secret for JWT signing (min 32 chars) | Yes |
| `GOOGLE_API_KEY` | Google Gemini API key | Yes |
| `QWEN_BASE_URL` | vLLM endpoint for Qwen | Yes |
| `MLFLOW_TRACKING_URI` | MLFlow server URL | Yes |
| `CORS_ORIGINS` | Allowed CORS origins | Yes |

## License

Private -- All rights reserved.
