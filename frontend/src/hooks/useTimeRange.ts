/** The selected time range, kept in the URL (?range=24h) so views can be shared. */
import { useSearchParams } from 'react-router';

export const RANGES = [
  { id: '1h', label: '1h', hours: 1 },
  { id: '24h', label: '24h', hours: 24 },
  { id: '7d', label: '7d', hours: 24 * 7 },
  { id: '30d', label: '30d', hours: 24 * 30 },
] as const;

export type RangeId = (typeof RANGES)[number]['id'];

export function useTimeRange(fallback: RangeId = '24h') {
  const [params, setParams] = useSearchParams();
  const id = (RANGES.find((r) => r.id === params.get('range'))?.id ?? fallback) as RangeId;
  const range = RANGES.find((r) => r.id === id) ?? RANGES[1];
  const setRange = (next: RangeId) =>
    setParams(
      (p) => {
        p.set('range', next);
        return p;
      },
      { replace: true },
    );
  return { range, setRange };
}
