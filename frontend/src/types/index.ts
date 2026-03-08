/**
 * Module: index.ts (Types)
 * Purpose: Global TypeScript interfaces mapping backend schemas.
 * WHY: Enforces type safety across the frontend to prevent runtime undefined errors.
 */

export interface User {
  id: string;
  company_id: string;
  email: string;
}

export interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
  setAuth: (token: string) => void;
  logout: () => void;
}

export interface MetricSummary {
  total_cost_usd: number;
  avg_latency_ms: number;
  total_requests: number;
  error_rate_pct: number;
  model_breakdown: {
    qwen: { requests: number; cost: number };
    gemini: { requests: number; cost: number };
  };
}

export interface LogEntry {
  log_id: string;
  timestamp: string;
  model_name: string;
  prompt_preview: string;
  response_preview: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  success: boolean;
  error_type: string;
}


// ── Agent Types ───────────────────────────────────────────

export interface AgentEvent {
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

export interface AgentRunSummary {
  run_id: string;
  total_steps: number;
  total_latency_ms: number;
  total_tokens: number;
  total_cost_usd: number;
  tools_used: string[];
  model_used: string;
  success: boolean;
}

export interface AgentRunRequest {
  prompt: string;
  model: 'qwen' | 'gemini';
  tools: string[];
  max_iterations: number;
}

export interface AgentTrace {
  run_id: string;
  company_id: string;
  timestamp: string;
  prompt: string;
  model_used: string;
  tools_enabled: string[];
  tools_used: string[];
  total_steps: number;
  total_latency_ms: number;
  total_tokens: number;
  total_cost_usd: number;
  success: boolean;
  final_answer?: string;
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
