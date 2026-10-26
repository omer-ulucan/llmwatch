import { useQuery } from '@tanstack/react-query';
import { authApi } from '@/api/auth';
import { useStore } from '@/store/useStore';

/** The signed-in user and workspace (GET /auth/me). */
export function useMe() {
  const isAuthenticated = useStore((s) => s.isAuthenticated);
  return useQuery({
    queryKey: ['me'],
    queryFn: authApi.me,
    enabled: isAuthenticated,
    staleTime: 5 * 60_000,
  });
}
