/**
 * Module: query.ts
 * Purpose: The shared TanStack Query client.
 * WHY: One cache for server state gives every page loading/error states, request
 * deduplication and refetch-on-focus without hand-written effects.
 */
import { QueryClient } from '@tanstack/react-query';
import axios from 'axios';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: true,
      // Don't retry what retrying can't fix (auth, validation, not found).
      retry: (failureCount, error) => {
        if (axios.isAxiosError(error) && error.response && error.response.status < 500) return false;
        return failureCount < 2;
      },
    },
  },
});
