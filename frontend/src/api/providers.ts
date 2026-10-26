/**
 * Module: providers.ts (API)
 * Purpose: LLM providers and the model catalogue.
 */
import { apiClient } from './client';
import type { Capabilities, ConnectionTest, ModelCatalog, ModelInfo, Preset, Provider } from '@/types';

export interface ProviderInput {
  name: string;
  preset: string;
  base_url?: string | null;
  api_key?: string | null;
  enabled?: boolean;
}

export interface ModelInput {
  provider_id?: string;
  model_id?: string;
  display_name?: string;
  context_window?: number | null;
  capabilities?: Capabilities;
  input_price_per_mtok?: number | null;
  output_price_per_mtok?: number | null;
  open_weights?: boolean;
  is_default?: boolean;
  enabled?: boolean;
}

export const providersApi = {
  presets: () =>
    apiClient.get<{ presets: Preset[] }>('/providers/presets').then((r) => r.data.presets),
  list: () => apiClient.get<Provider[]>('/providers').then((r) => r.data),
  create: (input: ProviderInput) =>
    apiClient.post<Provider>('/providers', input).then((r) => r.data),
  update: (id: string, input: Partial<ProviderInput>) =>
    apiClient.patch<Provider>(`/providers/${id}`, input).then((r) => r.data),
  remove: (id: string) => apiClient.delete(`/providers/${id}`),
  test: (id: string) =>
    apiClient.post<ConnectionTest>(`/providers/${id}/test`).then((r) => r.data),
  discover: (id: string) =>
    apiClient
      .post<{ discovered: string[]; added: string[] }>(`/providers/${id}/discover`)
      .then((r) => r.data),
};

export const modelsApi = {
  catalog: (params: { available_only?: boolean } = {}) =>
    apiClient.get<ModelCatalog>('/models', { params }).then((r) => r.data),
  create: (input: ModelInput) => apiClient.post<ModelInfo>('/models', input).then((r) => r.data),
  update: (id: string, input: ModelInput) =>
    apiClient.patch<ModelInfo>(`/models/${id}`, input).then((r) => r.data),
  remove: (id: string) => apiClient.delete(`/models/${id}`),
};
