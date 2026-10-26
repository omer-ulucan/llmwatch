/**
 * Module: auth.ts (API)
 * Purpose: Sign-in, sign-up and the current user.
 */
import { apiClient } from './client';
import type { Me, TokenResponse } from '@/types';

export const authApi = {
  login: (email: string, password: string) =>
    apiClient.post<TokenResponse>('/auth/login', { email, password }).then((r) => r.data),

  register: (email: string, password: string, workspaceName: string) =>
    apiClient
      .post<{ workspace_id: string }>('/auth/register', {
        email,
        password,
        workspace_name: workspaceName,
      })
      .then((r) => r.data),

  me: () => apiClient.get<Me>('/auth/me').then((r) => r.data),
};

export const workspaceApi = {
  delete: (confirmName: string) =>
    apiClient.delete('/workspaces/current', { data: { confirm_name: confirmName } }),
};
