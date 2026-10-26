/**
 * Module: analytics.ts (API)
 * Purpose: Usage metrics over a time window, the call log and CSV export.
 */
import { apiClient } from './client';
import type { FilterOptions, LogPage, MetricSummary, Timeseries } from '@/types';

export interface AnalyticsFilters {
  hours?: number;
  model?: string;
  provider?: string;
  source?: string;
  status?: 'success' | 'error' | 'cancelled';
  q?: string;
}

/** Drops empty values so the URL only carries what's set. */
export function cleanParams<T extends object>(params: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  ) as Partial<T>;
}

export const analyticsApi = {
  summary: (filters: AnalyticsFilters) =>
    apiClient
      .get<MetricSummary>('/analytics/summary', { params: cleanParams(filters) })
      .then((r) => r.data),

  timeseries: (filters: AnalyticsFilters) =>
    apiClient
      .get<Timeseries>('/analytics/timeseries', { params: cleanParams(filters) })
      .then((r) => r.data),

  logs: (filters: AnalyticsFilters & { page: number; page_size: number }) =>
    apiClient.get<LogPage>('/analytics/logs', { params: cleanParams(filters) }).then((r) => r.data),

  filters: (hours: number) =>
    apiClient.get<FilterOptions>('/analytics/filters', { params: { hours } }).then((r) => r.data),

  /** Downloads the filtered log as CSV (with auth, so not a plain link). */
  async exportCsv(filters: AnalyticsFilters): Promise<void> {
    const response = await apiClient.get<Blob>('/analytics/logs.csv', {
      params: cleanParams(filters),
      responseType: 'blob',
    });
    const disposition = String(response.headers['content-disposition'] ?? '');
    const match = /filename="([^"]+)"/.exec(disposition);
    const url = URL.createObjectURL(response.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = match?.[1] ?? 'llmwatch-logs.csv';
    link.click();
    URL.revokeObjectURL(url);
  },
};
