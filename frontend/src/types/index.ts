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
