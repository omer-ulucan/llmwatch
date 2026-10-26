/**
 * Module: format.ts
 * Purpose: Consistent number, cost, duration and date formatting.
 * WHY: Costs per call are often fractions of a cent; showing "$0.00" hides them.
 * Missing values render as an em dash rather than a misleading zero.
 */
import { formatDistanceToNowStrict } from 'date-fns';

export const DASH = '—';

/** USD with enough precision for tiny per-call costs. */
export function formatCost(usd: number | null | undefined): string {
  if (usd === null || usd === undefined || Number.isNaN(usd)) return DASH;
  if (usd === 0) return '$0';
  const abs = Math.abs(usd);
  if (abs >= 1) return `$${usd.toFixed(2)}`;
  if (abs >= 0.01) return `$${usd.toFixed(4)}`;
  // Two significant digits for sub-cent values, e.g. $0.00012
  const digits = Math.min(8, Math.max(2, 1 - Math.floor(Math.log10(abs))));
  return `$${usd.toFixed(digits)}`;
}

export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return DASH;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`;
  return `${(ms / 60_000).toFixed(1)} min`;
}

export function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return DASH;
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(n);
}

export function formatCompact(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return DASH;
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(n);
}

/** A 0..1 ratio as a percentage. */
export function formatRatio(ratio: number | null | undefined, digits = 1): string {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return DASH;
  return `${(ratio * 100).toFixed(digits)}%`;
}

/** A value that is already a percentage (e.g. 12.5 -> "12.5%"). */
export function formatPct(pct: number | null | undefined, digits = 1): string {
  if (pct === null || pct === undefined || Number.isNaN(pct)) return DASH;
  return `${pct.toFixed(digits)}%`;
}

/** Signed change, e.g. "+12.3%" / "-4.0%". */
export function formatSignedPct(pct: number | null | undefined, digits = 1): string {
  if (pct === null || pct === undefined || Number.isNaN(pct)) return DASH;
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(digits)}%`;
}

export function formatSigned(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}`;
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return DASH;
  return `${formatDistanceToNowStrict(date)} ago`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return DASH;
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
