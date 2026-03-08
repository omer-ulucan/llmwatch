# LLMWatch Agent Capabilities + Observability Tracing Plan

> **Goal**: Add a ReAct agent with 4 tools (web search, code execution, database query, document analysis) to LLMWatch, with full execution tracing streamed to the frontend via SSE and stored in DynamoDB for a dedicated trace viewer UI.
>
> **Philosophy**: The agent is both a feature AND a demo of the observability platform. "Eat your own dog food" — every agent step is traced, stored, and visualizable.

---

## Architecture Overview

```
User clicks "Agent Mode" in Chat UI
        │
        ▼
POST /agent/run  (SSE stream)
        │
        ▼
┌──────────────────────────────────────────────┐
│  AgentService (LangChain ReAct AgentExecutor) │
│                                              │
│  Tools:                                      │
│    🔍 web_search    (DuckDuckGo)             │
│    🐍 code_execute  (subprocess sandbox)     │
│    📊 db_query      (DynamoDB log analytics) │
│    📄 doc_analyze   (URL fetch + summarize)  │
│                                              │
│  Callbacks:                                  │
│    TracingCallback → SSE stream + DynamoDB   │
└──────────────────────────────────────────────┘
        │
        ▼ (each step streamed as SSE event)
┌─────────────────────┐
│  Frontend Agent UI   │
│  - Real-time steps   │
│  - Tool call results │
│  - Final answer      │
└─────────────────────┘
        │
        ▼ (after completion)
┌─────────────────────────────┐
│  DynamoDB: agent_traces     │
│  PK: company_id             │
│  SK: run_id#step_index      │
│  + MLFlow nested runs       │
└─────────────────────────────┘
        │
        ▼
┌─────────────────────┐
│  /traces UI page     │
│  - Timeline view     │
│  - Step details      │
│  - Cost breakdown    │
│  - Tool usage stats  │
└─────────────────────┘
```

---

## Phase 1: Backend — Agent Tools (4 tools)

### 1.1 New file: `backend/tools/__init__.py`

Empty init.

### 1.2 New file: `backend/tools/web_search.py`

- Use `duckduckgo-search` package (add to requirements.txt)
- Create a LangChain `@tool` decorated function: `web_search(query: str) -> str`
- Returns top 3-5 results with titles + snippets + URLs
- Timeout: 10 seconds
- Catches exceptions gracefully (returns error string, doesn't crash the agent)

### 1.3 New file: `backend/tools/code_executor.py`

- Create a LangChain `@tool` decorated function: `execute_python(code: str) -> str`
- Runs Python code in a subprocess with:
  - `subprocess.run()` with `timeout=15` seconds
  - `stdout` + `stderr` captured
  - Resource limits: no network access (optional), max output 10KB
  - Runs with `python -c <code>` (not eval/exec in the main process)
- Returns stdout or error message
- **Security**: Never runs in the main process. Subprocess isolation is sufficient for a hackathon demo. Log a warning comment about production needing Docker isolation.

### 1.4 New file: `backend/tools/db_query.py`

- Create a LangChain `@tool` decorated function: `query_llm_logs(question: str) -> str`
- Takes a natural language question about the user's LLM usage data
- Implementation:
  - Fetches recent logs from DynamoDB (last 100, using existing `dynamo_service.get_logs()`)
  - Formats them into a summary string the agent can reason about
  - Answers questions like "What's my most expensive model?", "How many requests did I make today?", "What's my average latency?"
- The agent itself interprets the data — no separate LLM call needed
- Needs `company_id` injected (passed from the authenticated user context)

### 1.5 New file: `backend/tools/doc_analyzer.py`

- Create a LangChain `@tool` decorated function: `analyze_document(url: str) -> str`
- Fetches a URL using `httpx` (async) or `urllib.request`
- Extracts text content (strip HTML tags with a simple regex or `html.parser`)
- Truncates to first 5000 chars to stay within context window
- Returns the extracted text for the agent to reason about
- Timeout: 15 seconds
- Handles common errors (404, timeout, invalid URL)

### 1.6 New dependency: `backend/requirements.txt`

Add:
```
duckduckgo-search>=7.0.0
```

(httpx is already in requirements.txt)

---

## Phase 2: Backend — Agent Service

### 2.1 New file: `backend/services/agent_service.py`

The core agent orchestration service.

```python
class AgentService:
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service

    async def run_agent(
        self,
        prompt: str,
        model: str,           # "qwen" or "gemini"
        company_id: str,
        tools: List[str],     # ["web_search", "code_execute", "db_query", "doc_analyze"]
        max_iterations: int = 10,
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Runs a ReAct agent and yields AgentEvent objects for each step.
        These events are streamed to the frontend via SSE.
        """
```

**Implementation details**:

1. **LLM selection**: Reuse the existing strategy pattern. Get the LangChain `ChatOpenAI` or `ChatGoogleGenerativeAI` instance from the corresponding strategy. Both support tool calling.
   - For Qwen via vLLM: `ChatOpenAI` with the vLLM base URL (already configured)
   - For Gemini: `ChatGoogleGenerativeAI` (already configured)

2. **Agent creation**: Use `langchain.agents.create_react_agent()` with:
   - The selected LLM
   - The filtered tool list (based on user's `tools` selection)
   - A ReAct prompt template (use `langchain.hub.pull("hwchase17/react")` or define a custom one)

3. **Agent execution**: Use `AgentExecutor` with:
   - `max_iterations=max_iterations`
   - `handle_parsing_errors=True` (graceful recovery from bad LLM outputs)
   - `return_intermediate_steps=True` (captures the full trace)

4. **Custom callback handler**: `TracingCallbackHandler` (see Phase 3) attached to the agent run. This callback:
   - Yields SSE events for each step (thinking, tool call, tool result, final answer)
   - Accumulates trace data for DynamoDB storage

5. **Tool instantiation**: Create tool instances with `company_id` injected where needed (db_query needs it). Use a factory pattern:
   ```python
   def build_tools(company_id: str, enabled_tools: List[str]) -> List[BaseTool]:
       available = {
           "web_search": web_search_tool,
           "code_execute": code_execute_tool,
           "db_query": make_db_query_tool(company_id),  # closure over company_id
           "doc_analyze": doc_analyze_tool,
       }
       return [available[t] for t in enabled_tools if t in available]
   ```

6. **Singleton + factory**:
   ```python
   agent_service = AgentService(llm_service)

   def get_agent_service() -> AgentService:
       return agent_service
   ```

---

## Phase 3: Backend — Tracing Callback + SSE Events

### 3.1 New file: `backend/services/tracing_service.py`

**Data model** — `AgentEvent` (Pydantic model, also used as SSE payload):

```python
class AgentEvent(BaseModel):
    run_id: str                          # UUID for the entire agent run
    step_index: int                      # 0-based step counter
    event_type: Literal[
        "run_start",                     # Agent execution begins
        "thinking",                      # LLM is reasoning (the "Thought:" in ReAct)
        "tool_call",                     # Agent decided to call a tool
        "tool_result",                   # Tool returned a result
        "final_answer",                  # Agent produced final answer
        "error",                         # Something went wrong
        "run_end",                       # Agent execution complete (summary metrics)
    ]
    content: str                         # The actual text/data for this step
    tool_name: Optional[str] = None      # Which tool (for tool_call/tool_result)
    tool_input: Optional[str] = None     # Tool input args (for tool_call)
    latency_ms: Optional[float] = None   # Time for this step
    tokens: Optional[int] = None         # Tokens used in this step (LLM steps only)
    cost_usd: Optional[float] = None     # Cost for this step
    timestamp: str                       # ISO timestamp
```

**`run_end` event** carries summary metrics:
```python
class AgentRunSummary(BaseModel):
    run_id: str
    total_steps: int
    total_latency_ms: float
    total_tokens: int
    total_cost_usd: float
    tools_used: List[str]
    model_used: str
    success: bool
```

### 3.2 `TracingCallbackHandler` (in same file)

Extends `langchain.callbacks.base.BaseCallbackHandler`:

- `on_agent_action(action)` → yield `tool_call` event
- `on_tool_end(output)` → yield `tool_result` event
- `on_llm_start(...)` → record start time
- `on_llm_end(response)` → yield `thinking` event with token counts
- `on_agent_finish(finish)` → yield `final_answer` event
- `on_chain_error(error)` → yield `error` event

The handler accumulates all events in a list. After the agent finishes, the router saves the full trace to DynamoDB.

### 3.3 DynamoDB trace storage

**New table**: `llmwatch_traces` (add to config.py as `dynamodb_table_traces`)

Schema:
- **PK**: `company_id` (String) — multi-tenant isolation
- **SK**: `run_ts#run_id` (String) — composite: ISO timestamp + run UUID, enables time-range queries
- **GSI**: `run_id-index` on `run_id` — for fetching a specific trace by ID

**Item structure** (one item per agent run, steps stored as a JSON list attribute):
```json
{
    "company_id": "comp_123",
    "run_ts#run_id": "2026-03-07T14:30:00Z#abc-def-123",
    "run_id": "abc-def-123",
    "timestamp": "2026-03-07T14:30:00Z",
    "prompt": "Search the web for the latest AI news and summarize it",
    "model_used": "qwen",
    "tools_enabled": ["web_search", "doc_analyze"],
    "tools_used": ["web_search"],
    "total_steps": 4,
    "total_latency_ms": 3200,
    "total_tokens": 1500,
    "total_cost_usd": 0.0015,
    "success": true,
    "final_answer": "Here are the latest AI news...",
    "steps": [
        {
            "step_index": 0,
            "event_type": "thinking",
            "content": "I need to search for AI news...",
            "latency_ms": 450,
            "tokens": 120,
            "timestamp": "2026-03-07T14:30:00.100Z"
        },
        {
            "step_index": 1,
            "event_type": "tool_call",
            "tool_name": "web_search",
            "tool_input": "latest AI news March 2026",
            "timestamp": "2026-03-07T14:30:00.550Z"
        },
        {
            "step_index": 2,
            "event_type": "tool_result",
            "tool_name": "web_search",
            "content": "1. GPT-5 released...",
            "latency_ms": 1200,
            "timestamp": "2026-03-07T14:30:01.750Z"
        },
        {
            "step_index": 3,
            "event_type": "final_answer",
            "content": "Here are the latest AI news...",
            "latency_ms": 800,
            "tokens": 350,
            "timestamp": "2026-03-07T14:30:02.550Z"
        }
    ]
}
```

**Why one item per run (not one item per step)**: DynamoDB items can be up to 400KB. An agent trace with 10-20 steps fits easily. Single-item reads are faster and cheaper than multi-item queries. For the trace viewer, you always want the full trace anyway.

### 3.4 New methods in `dynamo_service.py`

```python
def save_trace(self, company_id: str, trace_data: Dict[str, Any]) -> str:
    """Save a complete agent trace."""

def get_traces(self, company_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch recent traces for a company (for the trace list view)."""

def get_trace_by_id(self, company_id: str, run_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single trace by run_id (for the trace detail view)."""
```

### 3.5 MLFlow nested runs

In the tracing callback, after the agent completes:
1. Create a parent MLFlow run named `agent-{model}-run`
2. Log top-level metrics: total_latency, total_tokens, total_cost, step_count, success
3. For each step that involved an LLM call, create a nested run with step-level metrics
4. Tag with tools_used, prompt_preview

This reuses the existing `mlflow_service.py` pattern but extends it.

---

## Phase 4: Backend — Agent Router + SSE Endpoint

### 4.1 New file: `backend/routers/agent.py`

**Endpoints**:

#### `POST /agent/run` — SSE streaming agent execution

```python
@router.post("/agent/run")
async def run_agent(
    request: AgentRunRequest,
    current_user: dict = Depends(get_current_user),
    agent_svc: AgentService = Depends(get_agent_service),
):
    """
    Runs a ReAct agent with the specified tools and streams events via SSE.
    Returns text/event-stream content type.
    """
```

- Content-Type: `text/event-stream`
- Returns `StreamingResponse` with an async generator
- Each SSE event is a JSON-serialized `AgentEvent`
- SSE format: `data: {json}\n\n`
- After the stream ends, a background task saves the trace to DynamoDB + MLFlow

#### `GET /agent/traces` — List recent traces

```python
@router.get("/agent/traces")
async def get_traces(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    dynamo_svc: DynamoDBService = Depends(get_dynamo_service),
):
    """Returns a list of recent agent traces for the authenticated user's company."""
```

#### `GET /agent/traces/{run_id}` — Get single trace detail

```python
@router.get("/agent/traces/{run_id}")
async def get_trace(
    run_id: str,
    current_user: dict = Depends(get_current_user),
    dynamo_svc: DynamoDBService = Depends(get_dynamo_service),
):
    """Returns the full trace for a specific agent run."""
```

#### `GET /agent/analytics` — Agent-specific analytics

```python
@router.get("/agent/analytics")
async def agent_analytics(
    current_user: dict = Depends(get_current_user),
    dynamo_svc: DynamoDBService = Depends(get_dynamo_service),
):
    """
    Returns aggregate agent metrics:
    - total_runs, success_rate, avg_steps, avg_latency, total_cost
    - tool_usage_breakdown (which tools used how often)
    - model_breakdown (qwen vs gemini for agent runs)
    """
```

### 4.2 New Pydantic schemas in `backend/models/schemas.py`

```python
class AgentRunRequest(BaseModel):
    prompt: str
    model: str                          # "qwen" or "gemini"
    tools: List[str] = ["web_search", "code_execute", "db_query", "doc_analyze"]
    max_iterations: int = 10
    thinking_mode: bool = False

    model_config = ConfigDict(extra="forbid")

    @field_validator("model")
    def validate_model(cls, v):
        if v not in ("qwen", "gemini"):
            raise ValueError("Model must be 'qwen' or 'gemini'")
        return v

    @field_validator("tools")
    def validate_tools(cls, v):
        valid = {"web_search", "code_execute", "db_query", "doc_analyze"}
        for t in v:
            if t not in valid:
                raise ValueError(f"Invalid tool: {t}")
        return v

    @field_validator("max_iterations")
    def validate_max_iterations(cls, v):
        if v < 1 or v > 20:
            raise ValueError("max_iterations must be between 1 and 20")
        return v
```

### 4.3 Register router in `main.py`

```python
from routers.agent import router as agent_router
app.include_router(agent_router, prefix="/agent", tags=["Agent"])
```

### 4.4 Update ALB routing (in the AWS deployment roadmap)

Add `/agent/*` to the path-based routing rule so ALB forwards agent requests to the backend.

---

## Phase 5: Backend — Config + Infra Updates

### 5.1 `backend/config.py`

Add:
```python
dynamodb_table_traces: str  # New table name, e.g., "llmwatch_traces"
```

And in `.env.example`:
```
DYNAMODB_TABLE_TRACES=llmwatch_traces
```

### 5.2 DynamoDB table creation (add to AWS deployment roadmap)

```bash
aws dynamodb create-table \
    --table-name llmwatch_traces \
    --attribute-definitions \
        AttributeName=company_id,AttributeType=S \
        AttributeName="run_ts#run_id",AttributeType=S \
        AttributeName=run_id,AttributeType=S \
    --key-schema \
        AttributeName=company_id,KeyType=HASH \
        AttributeName="run_ts#run_id",KeyType=RANGE \
    --global-secondary-indexes \
        '[{
            "IndexName": "run_id-index",
            "KeySchema": [{"AttributeName": "run_id", "KeyType": "HASH"}],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5}
        }]' \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
    --region us-east-1
```

### 5.3 Update `.env.example`

Add `DYNAMODB_TABLE_TRACES=llmwatch_traces`.

---

## Phase 6: Frontend — Agent Chat UI

### 6.1 New route: `/agent` (new file: `frontend/src/routes/agent.tsx`)

A dedicated agent chat page (separate from the simple `/chat`).

**Layout**: Two-pane layout similar to `/chat` but with:

**Left pane — Agent Configuration + Chat**:
- Model selector dropdown (Qwen / Gemini)
- Tool toggles (4 checkboxes with icons for each tool)
- Max iterations slider (1-20)
- Prompt input (textarea)
- "Run Agent" button
- Conversation display area showing:
  - User prompt
  - Streaming agent steps (thinking, tool calls, tool results)
  - Final answer

**Right pane — Live Trace Viewer**:
- Real-time step timeline as the agent executes
- Each step is a card showing:
  - Step type icon (brain for thinking, magnifying glass for search, code brackets for execution, etc.)
  - Step content (expandable for long content)
  - Latency badge
  - Token count badge (for LLM steps)
- After completion: summary card with total metrics

### 6.2 SSE client hook: `frontend/src/hooks/useAgentStream.ts`

Custom React hook that:
- Opens an EventSource / fetch with ReadableStream to `POST /agent/run`
- Note: Standard `EventSource` only supports GET. Use `fetch()` with `ReadableStream` for POST + SSE.
- Parses each SSE event into `AgentEvent` objects
- Updates state incrementally (steps array, current status, metrics)
- Handles errors and connection drops
- Returns: `{ steps, isRunning, error, summary, runAgent() }`

```typescript
interface AgentEvent {
    run_id: string;
    step_index: number;
    event_type: 'run_start' | 'thinking' | 'tool_call' | 'tool_result' | 'final_answer' | 'error' | 'run_end';
    content: string;
    tool_name?: string;
    tool_input?: string;
    latency_ms?: number;
    tokens?: number;
    cost_usd?: number;
    timestamp: string;
}

interface AgentRunSummary {
    run_id: string;
    total_steps: number;
    total_latency_ms: number;
    total_tokens: number;
    total_cost_usd: number;
    tools_used: string[];
    model_used: string;
    success: boolean;
}
```

### 6.3 Agent step components: `frontend/src/components/agent/`

- `AgentStepCard.tsx` — Single step display (icon + type badge + content + metrics)
- `AgentTimeline.tsx` — Vertical timeline of step cards with connecting lines
- `AgentToolBadge.tsx` — Tool name + icon badge
- `AgentSummaryCard.tsx` — Post-run summary with total metrics
- `AgentToolConfig.tsx` — Tool selection checkboxes with descriptions

Use Framer Motion for step entry animations (stagger as each step arrives from the stream).

---

## Phase 7: Frontend — Trace Viewer Page

### 7.1 New route: `/traces` (new file: `frontend/src/routes/traces.tsx`)

**Two-level UI**:

**Level 1 — Trace List** (default view):
- Table/list of recent agent runs
- Columns: Timestamp, Prompt (preview), Model, Tools Used (badges), Steps, Latency, Cost, Status (success/fail)
- Click a row to drill into Level 2
- Filter by: model, date range, status
- Pagination (load more)

**Level 2 — Trace Detail** (after clicking a trace):
- Full prompt displayed at top
- **Waterfall/timeline view** of all steps:
  - Horizontal timeline bar showing relative timing of each step
  - Each step is a row with: step type, tool name, duration bar, cost
  - Color-coded by type (blue=thinking, green=tool_call, orange=tool_result, purple=final_answer, red=error)
- **Step detail panel** (click a step to expand):
  - Full content of that step
  - For tool_calls: show input and output
  - For LLM steps: show token breakdown
- **Summary sidebar**:
  - Total cost, latency, tokens
  - Tool usage pie chart (Recharts)
  - Model info
  - Success/failure status

### 7.2 API client functions: `frontend/src/api/agent.ts`

```typescript
export const agentApi = {
    getTraces: (limit?: number) => apiClient.get('/agent/traces', { params: { limit } }),
    getTrace: (runId: string) => apiClient.get(`/agent/traces/${runId}`),
    getAgentAnalytics: () => apiClient.get('/agent/analytics'),
};
```

---

## Phase 8: Frontend — Dashboard Updates

### 8.1 Update `dashboard.tsx`

Add a new row of agent-specific KPI cards:
- **Agent Runs** (total in last 24h)
- **Agent Success Rate** (%)
- **Avg Steps per Run**
- **Agent Cost** (total in last 24h)

Fetch from `/agent/analytics` endpoint.

### 8.2 Add agent chart

Add a new chart: "Agent Tool Usage" — bar chart showing how often each tool is used.

---

## Phase 9: Frontend — Navigation Updates

### 9.1 Update sidebar (`frontend/src/components/Sidebar.tsx`)

Add two new navigation items:
- **Agent** (icon: Bot) → `/agent`
- **Traces** (icon: Activity/GitBranch) → `/traces`

### 9.2 Update router (`frontend/src/App.tsx` or wherever routes are defined)

Add routes:
```tsx
<Route path="/agent" element={<AgentPage />} />
<Route path="/traces" element={<TracesPage />} />
<Route path="/traces/:runId" element={<TraceDetailPage />} />
```

---

## Phase 10: Backend — Tests

### 10.1 New test files

- `backend/tests/test_tools.py` — Test each tool independently:
  - `test_web_search_returns_results` (mock the DuckDuckGo API)
  - `test_code_executor_basic_math` (real subprocess, `print(2+2)` → "4")
  - `test_code_executor_timeout` (infinite loop → timeout error string)
  - `test_code_executor_syntax_error` (bad code → error string)
  - `test_db_query_formats_logs` (mock DynamoDB, verify string output)
  - `test_doc_analyzer_fetches_url` (mock httpx, verify text extraction)
  - `test_doc_analyzer_handles_404` (mock httpx 404, verify error string)

- `backend/tests/test_agent_service.py` — Test agent orchestration:
  - `test_agent_yields_events` (mock LLM + tools, verify event sequence)
  - `test_agent_max_iterations_respected` (mock LLM to loop, verify it stops)
  - `test_agent_handles_tool_error_gracefully` (tool raises → agent recovers)
  - `test_agent_run_summary_metrics` (verify totals are correct)

- `backend/tests/test_tracing.py` — Test trace storage:
  - `test_save_and_retrieve_trace` (mock DynamoDB)
  - `test_trace_list_newest_first` (verify ordering)
  - `test_agent_analytics_aggregation` (verify metric calculations)

---

## Phase 11: Dependency Updates

### `backend/requirements.txt` additions

```
duckduckgo-search>=7.0.0
```

Note: `langchain`, `langchain-openai`, `httpx` are already present. The ReAct agent, tool decorators, and callback handlers are all part of `langchain` core.

### `frontend/package.json` — No new dependencies needed

Everything is already available: Recharts (charts), Framer Motion (animations), Lucide (icons), Axios (HTTP), date-fns (dates).

For SSE streaming, we'll use the native `fetch()` + `ReadableStream` API — no additional library needed.

---

## Implementation Order

The recommended implementation order, from backend to frontend:

| Step | What | Estimated Effort | Dependencies |
|------|------|-----------------|-------------|
| 1 | Tools (4 files) | Medium | requirements.txt update |
| 2 | Tracing service + AgentEvent models | Medium | Tools |
| 3 | Agent service | High | Tools + Tracing |
| 4 | Pydantic schemas (AgentRunRequest etc.) | Low | None |
| 5 | Agent router (SSE endpoint + trace endpoints) | High | Agent service + Schemas |
| 6 | Config updates (new table name) + .env.example | Low | None |
| 7 | Register router in main.py | Low | Router |
| 8 | DynamoDB methods (save_trace, get_traces, get_trace_by_id) | Medium | Config |
| 9 | Backend tests | Medium | All backend done |
| 10 | SSE client hook (useAgentStream) | Medium | Backend SSE working |
| 11 | Agent step components | Medium | Hook |
| 12 | Agent page (/agent) | High | Hook + Components |
| 13 | Trace viewer page (/traces) | High | API client |
| 14 | API client functions (agent.ts) | Low | None |
| 15 | Dashboard updates (agent KPIs) | Low | API client |
| 16 | Navigation + routing updates | Low | Pages |
| 17 | Verify all tests pass + frontend builds | Low | Everything |

---

## New Files Summary

### Backend (9 new files)
```
backend/tools/__init__.py
backend/tools/web_search.py
backend/tools/code_executor.py
backend/tools/db_query.py
backend/tools/doc_analyzer.py
backend/services/agent_service.py
backend/services/tracing_service.py
backend/routers/agent.py
backend/tests/test_tools.py
backend/tests/test_agent_service.py
backend/tests/test_tracing.py
```

### Frontend (8 new files)
```
frontend/src/routes/agent.tsx
frontend/src/routes/traces.tsx
frontend/src/hooks/useAgentStream.ts
frontend/src/api/agent.ts
frontend/src/components/agent/AgentStepCard.tsx
frontend/src/components/agent/AgentTimeline.tsx
frontend/src/components/agent/AgentToolConfig.tsx
frontend/src/components/agent/AgentSummaryCard.tsx
```

### Modified Files
```
backend/requirements.txt              (add duckduckgo-search)
backend/config.py                     (add dynamodb_table_traces)
backend/services/dynamo_service.py    (add save_trace, get_traces, get_trace_by_id)
backend/models/schemas.py             (add AgentRunRequest, AgentEvent, AgentRunSummary)
backend/main.py                       (register agent router)
.env.example                          (add DYNAMODB_TABLE_TRACES)
frontend/src/routes/dashboard.tsx     (add agent KPI cards)
frontend/src/components/Sidebar.tsx   (add Agent + Traces nav items)
frontend/src/App.tsx (or router file) (add new routes)
```

**Total: 17 new files + 9 modified files**

---

## Risk Notes

1. **ReAct agent with vLLM/Qwen**: Not all models handle ReAct prompting well. Qwen 3.5 35B should be capable, but if tool-calling format is unreliable, we may need to switch to function-calling mode or add output parsing retries. Gemini handles tool calling natively.

2. **SSE with POST**: Standard `EventSource` API only supports GET. We'll use `fetch()` with a `ReadableStream` reader, which is well-supported in modern browsers but slightly more code than `EventSource`.

3. **Code execution security**: Subprocess sandbox is sufficient for a hackathon demo but NOT production-ready. Document this clearly. For production, Docker isolation is mandatory.

4. **DynamoDB item size**: Agent traces with many steps could approach the 400KB item limit. The `steps` list is JSON-serialized within the item. Truncating tool results to 2KB each keeps us safe. With 20 steps max, worst case is ~50KB per trace — well within limits.

5. **LangChain version compatibility**: The codebase pins `langchain>=0.2.6`. The ReAct agent API (`create_react_agent`, `AgentExecutor`) is stable in 0.2.x. The `@tool` decorator is in `langchain_core.tools`. Should work without version bumps.
