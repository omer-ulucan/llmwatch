/**
 * Module: index.ts (Types)
 * Purpose: TypeScript shapes of the backend API.
 * WHY: Enforces type safety across the frontend to prevent runtime undefined errors.
 * Kept by hand, next to the API modules in src/api, and mirroring the backend
 * response shapes field for field.
 */

// ── Auth ──────────────────────────────────────────────────

export interface User {
  id: string | null;
  email: string | null;
  role: 'owner' | 'member' | string;
}

export interface WorkspaceInfo {
  id: string;
  name: string;
  created_at: string;
}

export interface Me {
  user: User;
  workspace: WorkspaceInfo;
  auth_method: 'jwt' | 'api_key';
}

export interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
  setAuth: (token: string) => void;
  logout: () => void;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

// ── Analytics ─────────────────────────────────────────────

export interface ModelBreakdownEntry {
  model: string;
  provider: string | null;
  requests: number;
  errors: number;
  cost: number;
  avg_latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  error_rate_pct: number;
}

export type ComparedMetric =
  | 'total_requests'
  | 'total_cost_usd'
  | 'avg_latency_ms'
  | 'p95_latency_ms'
  | 'error_rate_pct';

export interface MetricSummary {
  window: { from: string; to: string };
  total_cost_usd: number;
  avg_latency_ms: number;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  total_requests: number;
  total_errors: number;
  total_cancelled: number;
  error_rate_pct: number;
  input_tokens: number;
  output_tokens: number;
  /** Keyed by "Provider/model". */
  model_breakdown: Record<string, ModelBreakdownEntry>;
  previous: Record<ComparedMetric, number | null>;
  deltas_pct: Record<ComparedMetric, number | null>;
}

export interface TimeseriesBucket {
  ts: string;
  requests: number;
  errors: number;
  cost_usd: number;
  avg_latency_ms: number | null;
  input_tokens: number;
  output_tokens: number;
}

export interface Timeseries {
  window: { from: string; to: string };
  bucket_seconds: number;
  buckets: TimeseriesBucket[];
}

export interface LogEntry {
  log_id: string;
  timestamp: string;
  model_name: string;
  provider_name: string | null;
  source: 'chat' | 'agent' | 'eval' | string;
  prompt_preview: string;
  response_preview: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  success: boolean;
  error_type: string;
  error_message: string | null;
  status_code: number | null;
  thinking_mode: boolean;
}

export interface LogPage {
  items: LogEntry[];
  total: number;
  page: number;
  page_size: number;
}

export interface FilterOptions {
  models: string[];
  providers: string[];
}

// ── Providers and models ──────────────────────────────────

export interface Preset {
  id: string;
  label: string;
  base_url: string;
  requires_api_key: boolean;
  local: boolean;
  stream_usage: boolean;
  docs_url: string;
}

export interface Provider {
  id: string;
  name: string;
  preset: string;
  preset_label: string;
  base_url: string;
  has_api_key: boolean;
  api_key_masked: string | null;
  enabled: boolean;
  managed_by_env: boolean;
  local: boolean;
  created_at: string;
  updated_at: string;
}

export interface ConnectionTest {
  ok: boolean;
  latency_ms: number;
  model_count: number;
  models: string[];
  error: string | null;
  error_kind: string | null;
}

export interface Capabilities {
  tools: boolean;
  vision: boolean;
  reasoning: boolean;
  json_mode: boolean;
}

export interface ModelInfo {
  id: string;
  provider_id: string;
  provider_name: string;
  provider_preset: string;
  model_id: string;
  /** "Provider/model-id", accepted anywhere a model is expected. */
  ref: string;
  display_name: string;
  context_window: number | null;
  capabilities: Capabilities;
  input_price_per_mtok: number | null;
  output_price_per_mtok: number | null;
  priced: boolean;
  open_weights: boolean;
  local: boolean;
  is_default: boolean;
  enabled: boolean;
  available: boolean;
}

export interface ModelGroup {
  provider: Provider;
  models: ModelInfo[];
}

export interface ModelCatalog {
  groups: ModelGroup[];
  default_model_id: string | null;
}

// ── Chat ──────────────────────────────────────────────────

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface ChatRequest {
  model: string;
  prompt?: string;
  messages?: ChatMessage[];
  system_prompt?: string;
  thinking_mode?: boolean;
  temperature?: number;
  max_tokens?: number;
}

export type ChatStreamEvent =
  | { type: 'start'; model_used: string; model_id: string }
  | { type: 'delta'; text: string }
  | { type: 'reasoning'; text: string }
  | { type: 'usage'; input_tokens: number; output_tokens: number; reasoning_tokens: number }
  | { type: 'error'; error_type: string; message: string }
  | { type: 'done'; latency_ms: number; cost_usd: number; priced: boolean; finish_reason: string | null };

// ── Agent ─────────────────────────────────────────────────

export interface AgentEvent {
  run_id: string;
  step_index: number;
  event_type: 'run_start' | 'thinking' | 'tool_call' | 'tool_result' | 'final_answer' | 'error' | 'run_end';
  content: string;
  tool_name?: string;
  tool_input?: string;
  latency_ms?: number;
  tokens?: number;
  input_tokens?: number;
  output_tokens?: number;
  cost_usd?: number;
  is_error?: boolean;
  error_type?: string;
  timestamp: string;
}

export interface AgentRunSummary {
  run_id: string;
  total_steps: number;
  total_latency_ms: number;
  total_tokens: number;
  total_cost_usd: number;
  tools_used: string[];
  model_used: string;
  success: boolean;
  status?: 'success' | 'error' | 'cancelled';
  llm_calls?: number;
  priced?: boolean;
}

export interface AgentRunRequest {
  prompt: string;
  model: string;
  tools: string[];
  max_iterations: number;
}

export interface AgentToolInfo {
  name: string;
  description: string;
}

export interface AgentTrace {
  run_id: string;
  workspace_id: string;
  timestamp: string;
  prompt: string;
  model_used: string;
  tools_enabled: string[];
  tools_used: string[];
  status: 'running' | 'success' | 'error' | 'cancelled';
  total_steps: number;
  total_latency_ms: number;
  total_tokens: number;
  total_cost_usd: number;
  success: boolean;
  final_answer?: string;
  error?: string | null;
  steps?: AgentEvent[];
}

export interface AgentAnalytics {
  total_runs: number;
  success_rate: number;
  avg_steps: number;
  avg_latency_ms: number;
  total_cost_usd: number;
  tool_usage: Record<string, number>;
  model_breakdown: Record<string, number>;
}

// ── Evals ─────────────────────────────────────────────────

export interface AssertionDoc {
  type: string;
  value?: unknown;
  weight?: number;
  [option: string]: unknown;
}

export interface CaseDoc {
  id: string;
  vars: Record<string, unknown>;
  expected?: string;
  assert?: AssertionDoc[];
  tags?: string[];
}

export interface SuiteDocument {
  name: string;
  description?: string;
  system_prompt?: string;
  prompt: string;
  assert?: AssertionDoc[];
  cases: CaseDoc[];
}

export interface SuiteSummary {
  id: string;
  name: string;
  description: string;
  latest_version: number;
  baseline_run_id: string | null;
  case_count: number | null;
  created_at: string;
  updated_at: string;
}

export interface SuiteVersionInfo {
  version: number;
  id: string;
  created_at: string;
  case_count: number;
}

export interface SuiteDetail extends SuiteSummary {
  version: number;
  version_id: string;
  definition: SuiteDocument;
  versions: SuiteVersionInfo[];
  created_version?: boolean;
  created_suite?: boolean;
}

export type RunStatus =
  | 'pending'
  | 'running'
  | 'cancelling'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'interrupted';

export interface EvalRun {
  id: string;
  suite_id: string;
  suite_version_id: string;
  group_id: string | null;
  label: string;
  status: RunStatus;
  variant: {
    model: string;
    model_label: string;
    model_id: string;
    provider: string;
    params: Record<string, number>;
    thinking?: boolean;
    judge_model?: string | null;
    use_cache?: boolean;
  };
  repeats: number;
  concurrency: number;
  pricing_snapshot: {
    input_price_per_mtok: number | null;
    output_price_per_mtok: number | null;
  };
  total_items: number;
  completed_items: number;
  failed_items: number;
  mean_score: number | null;
  pass_rate: number | null;
  total_cost_usd: number;
  total_tokens: number;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface EvaluatorResult {
  type: string;
  score: number;
  passed: boolean;
  reason: string;
  weight: number;
  warnings?: string[];
  error?: boolean;
}

export interface EvalResultItem {
  id: string;
  case_id: string;
  repeat_index: number;
  vars: Record<string, unknown>;
  expected: string | null;
  tags: string[];
  output: string;
  reasoning: string | null;
  score: number;
  passed: boolean;
  error: string | null;
  cached: boolean;
  latency_ms: number;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  evaluator_results: EvaluatorResult[];
}

export interface ResultPage {
  total: number;
  page: number;
  page_size: number;
  items: EvalResultItem[];
}

export interface VariantInput {
  model: string;
  label?: string;
  temperature?: number;
  max_tokens?: number;
  thinking?: boolean;
}

export interface CaseComparison {
  case_id: string;
  baseline_score: number;
  candidate_score: number;
  delta: number;
  baseline_passed: boolean;
  candidate_passed: boolean;
  change: 'fixed' | 'regressed' | 'unchanged';
  baseline_errors: number;
  candidate_errors: number;
}

export interface RunInfo {
  id: string;
  label: string;
  status: RunStatus;
  model: string;
  params: Record<string, number>;
  mean_score: number | null;
  pass_rate: number | null;
  total_cost_usd: number;
  created_at: string;
}

export interface Comparison {
  baseline: RunInfo;
  candidate: RunInfo;
  same_suite_version: boolean;
  paired_cases: number;
  baseline_only: string[];
  candidate_only: string[];
  score: {
    baseline_mean: number | null;
    candidate_mean: number | null;
    delta: number;
    ci_low: number;
    ci_high: number;
    confidence: number;
    resamples: number;
    significant: boolean;
  };
  pass_rate: {
    baseline: number;
    candidate: number;
    delta: number;
    regressions: number;
    fixes: number;
    p_value: number;
    test: 'exact' | 'chi2_cc' | 'none';
    significant: boolean;
    alpha: number;
  };
  cost: {
    baseline_per_case: number | null;
    candidate_per_case: number | null;
    delta_per_case: number;
    delta_pct: number | null;
    baseline_priced: boolean;
    candidate_priced: boolean;
  };
  latency: {
    baseline_mean_ms: number | null;
    candidate_mean_ms: number | null;
    delta_ms: number;
    delta_pct: number | null;
  };
  verdict: 'improved' | 'regressed' | 'no_significant_difference';
  warnings: string[];
  cases: CaseComparison[];
}

// ── API keys ──────────────────────────────────────────────

export interface ApiKey {
  key_id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at?: string;
  request_count: number;
  is_active: boolean;
}

export interface CreateApiKeyResponse {
  key_id: string;
  name: string;
  raw_key: string;
  prefix: string;
  created_at: string;
}
