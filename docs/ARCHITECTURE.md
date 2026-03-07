# LLMWatch Architecture

## System Diagram

```ascii
                      +------------------+
                      |                  |
                      |   React 19 SPA   |  (Frontend - React Router v7, Zustand, tailwind v4)
                      |  (awwwards UI)   |
                      |                  |
                      +-------+----------+
                              |
                        JWT / REST API
                              |
                      +-------v----------+
                      |                  |
                      |  FastAPI Server  |  (Backend - Python 3.11, Pydantic)
                      |  (Dependencies)  |
                      |                  |
                      +-------+----------+
                              |
          +-------------------+-------------------+
          |                   |                   |
  +-------v-------+   +-------v-------+   +-------v-------+
  |               |   |               |   |               |
  |  LLM Strategy |   |  DynamoDB     |   |    MLFlow     |
  |  (LangChain)  |   |  Service      |   |   Service     |
  |               |   |               |   |               |
  +---+-------+---+   +-------+-------+   +-------+-------+
      |       |               |                   |
+-----v---+ +-v-------+       |                   |
|  Qwen   | | Gemini  |       |                   |
| (vLLM)  | | (Google)|       v                   v
+---------+ +---------+  [ AWS Cloud ]     [ Local Docker ]
```

## Components

### 1. Frontend (React 19 + TypeScript + Vite)
- **Framework**: Bootstrapped via Vite holding strict type compliance.
- **Routing**: Adopted React Router v7 (Data API) for efficient component splitting.
- **State Management**: Zustand is utilized for memory-stored JWT session variables and Sidebar toggle tracking.
- **Styling**: Tailwind v4 serves as the global styling tool via pure CSS configurations. Framer Motion manages all complex micro-interactions, specifically optimized for layout animations (e.g. reasoning traces, dynamic layout routing).
- **Data Visualization**: Recharts provides un-opinionated standard SVG graphing for live cost and latency tracking.

### 2. API Layer (FastAPI)
- **Validation**: Strict Pydantic configurations explicitly forbid injection fields.
- **Security**: Embedded OAuth2 standard Bearer scheme, protected centrally via `auth/dependencies.py`. Implemented Helmet-style defensive headers including HSTS, XSS protections, and CSP protocols.
- **Rate Limiting**: Integrated `slowapi` ensuring IP-based traffic control before hitting database layers.

### 3. Core Services
- **LLM Strategy**: We abstracted model routing enabling dynamic swaps between the self-hosted `vLLM` infrastructure (Qwen3.5) and managed Google instances (Gemini 3 Flash).
- **DynamoDB Repository**: Centralized through Boto3, all read/write interactions are decoupled for secure NoSQL insertions using parameterized definitions, preventing injection vectors entirely.
- **MLFlow Metrics**: Executes asynchronously alongside inference tasks, writing structured JSON parameters over REST instead of blocking client requests. 

### 4. Container Orchestration
- Managed natively through Docker Compose. The `backend` image is secured utilizing standard non-root `appuser` configurations. `frontend` utilizes a dedicated `nginx` Alpine proxy executing optimized static caching. `mlflow` sits on a dedicated SQLite binding via local port allocation.
