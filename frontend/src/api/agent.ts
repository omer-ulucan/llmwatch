/**
 * Module: agent.ts (API)
 * Purpose: API client functions for agent trace endpoints.
 * WHY: Separates HTTP concerns from UI components, making them easier to test and mock.
 */
import { apiClient } from './client';
import type { AgentTrace, AgentAnalytics } from '@/types';

export const agentApi = {
  /**
   * Fetch recent traces for the trace list view.
   * WHY: The list endpoint strips the heavy 'steps' array for performance.
   */
  getTraces: (limit = 50) =>
    apiClient.get<{ traces: AgentTrace[] }>('/agent/traces', { params: { limit } }),

  /**
   * Fetch a single trace with full step detail for the waterfall view.
   */
  getTrace: (runId: string) =>
    apiClient.get<{ trace: AgentTrace }>(`/agent/traces/${runId}`),

  /**
   * Fetch aggregate agent metrics for the dashboard KPI cards.
   */
  getAgentAnalytics: () =>
    apiClient.get<AgentAnalytics>('/agent/analytics'),
};
