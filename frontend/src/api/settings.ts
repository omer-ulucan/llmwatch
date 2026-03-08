/**
 * Module: settings.ts (API)
 * Purpose: API client functions for API key management endpoints.
 * WHY: Separates HTTP concerns from UI components, making them easier to test and mock.
 */
import { apiClient } from './client';
import type { ApiKey, CreateApiKeyResponse } from '@/types';

export const settingsApi = {
  /**
   * Create a new API key. The raw key is returned ONCE in the response.
   * WHY: The raw key must be shown to the user immediately — it is never retrievable again.
   */
  createApiKey: (name: string) =>
    apiClient.post<CreateApiKeyResponse>('/api-keys', { name }),

  /**
   * List all API keys for the current company.
   * WHY: The settings page needs masked keys with usage stats for display.
   */
  listApiKeys: () =>
    apiClient.get<{ keys: ApiKey[] }>('/api-keys'),

  /**
   * Regenerate an API key — revokes old, returns new raw key ONCE.
   * WHY: Key rotation is a security best practice for compromised or aging keys.
   */
  regenerateApiKey: (keyId: string) =>
    apiClient.post<CreateApiKeyResponse>(`/api-keys/${keyId}/regenerate`),

  /**
   * Permanently revoke (delete) an API key.
   * WHY: Hard delete ensures the key can never authenticate again.
   */
  revokeApiKey: (keyId: string) =>
    apiClient.delete(`/api-keys/${keyId}`),
};
