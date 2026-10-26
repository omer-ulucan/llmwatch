/**
 * Module: evals.ts (API)
 * Purpose: Eval suites, runs, results and comparisons.
 */
import { apiClient } from './client';
import type {
  Comparison,
  EvalRun,
  ResultPage,
  SuiteDetail,
  SuiteDocument,
  SuiteSummary,
  VariantInput,
} from '@/types';

export interface StartRunsInput {
  suite_id: string;
  version?: number;
  variants: VariantInput[];
  repeats?: number;
  concurrency?: number;
  judge_model?: string;
  use_cache?: boolean;
}

export const evalsApi = {
  suites: () =>
    apiClient.get<{ suites: SuiteSummary[] }>('/evals/suites').then((r) => r.data.suites),
  suite: (id: string, version?: number) =>
    apiClient
      .get<SuiteDetail>(`/evals/suites/${id}`, { params: version ? { version } : {} })
      .then((r) => r.data),
  create: (doc: SuiteDocument) =>
    apiClient.post<SuiteDetail>('/evals/suites', doc).then((r) => r.data),
  update: (id: string, doc: SuiteDocument) =>
    apiClient.put<SuiteDetail>(`/evals/suites/${id}`, doc).then((r) => r.data),
  remove: (id: string) => apiClient.delete(`/evals/suites/${id}`),
  import: (content: string, format: 'yaml' | 'json') =>
    apiClient
      .post<SuiteDetail>('/evals/suites/import', { content, format })
      .then((r) => r.data),
  exportText: (id: string, format: 'yaml' | 'json', version?: number) =>
    apiClient
      .get<string>(`/evals/suites/${id}/export`, {
        params: { format, ...(version ? { version } : {}) },
        responseType: 'text',
        transformResponse: (data: string) => data,
      })
      .then((r) => r.data),
  setBaseline: (suiteId: string, runId: string | null) =>
    apiClient.put<SuiteSummary>(`/evals/suites/${suiteId}/baseline`, { run_id: runId }).then((r) => r.data),

  runs: (suiteId?: string) =>
    apiClient
      .get<{ runs: EvalRun[] }>('/evals/runs', { params: suiteId ? { suite_id: suiteId } : {} })
      .then((r) => r.data.runs),
  run: (id: string) => apiClient.get<EvalRun>(`/evals/runs/${id}`).then((r) => r.data),
  startRuns: (input: StartRunsInput) =>
    apiClient.post<{ runs: EvalRun[] }>('/evals/runs', input).then((r) => r.data.runs),
  results: (id: string, params: { status?: string; page?: number; page_size?: number }) =>
    apiClient.get<ResultPage>(`/evals/runs/${id}/results`, { params }).then((r) => r.data),
  cancel: (id: string) => apiClient.post(`/evals/runs/${id}/cancel`),
  resume: (id: string, retryErrors = false) =>
    apiClient.post<EvalRun>(`/evals/runs/${id}/resume`, null, {
      params: { retry_errors: retryErrors },
    }),
  removeRun: (id: string) => apiClient.delete(`/evals/runs/${id}`),
  compare: (baseline: string, candidate: string) =>
    apiClient
      .get<Comparison>('/evals/compare', { params: { baseline, candidate } })
      .then((r) => r.data),
};
