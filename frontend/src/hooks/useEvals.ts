import { useQuery } from '@tanstack/react-query';
import { evalsApi } from '@/api/evals';
import { isActiveStatus } from '@/lib/evals';

export function useSuites() {
  return useQuery({ queryKey: ['eval-suites'], queryFn: evalsApi.suites });
}

export function useSuite(id: string, version?: number) {
  return useQuery({ queryKey: ['eval-suite', id, version ?? 'latest'], queryFn: () => evalsApi.suite(id, version) });
}

/** Runs (all, or one suite's); polls while any is still running. */
export function useRuns(suiteId?: string) {
  return useQuery({
    queryKey: ['eval-runs', suiteId ?? 'all'],
    queryFn: () => evalsApi.runs(suiteId),
    refetchInterval: (query) => (query.state.data?.some((r) => isActiveStatus(r.status)) ? 2000 : false),
  });
}

export function useRun(id: string) {
  return useQuery({
    queryKey: ['eval-run', id],
    queryFn: () => evalsApi.run(id),
    refetchInterval: (query) => (query.state.data && isActiveStatus(query.state.data.status) ? 1500 : false),
  });
}
