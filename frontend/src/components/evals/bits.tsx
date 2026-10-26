/**
 * Small eval UI pieces: run status, score sparkline, CI bar, progress.
 */
import React from 'react';
import { Badge } from '@/components/ui';
import { cn } from '@/lib/cn';
import { formatSigned } from '@/lib/format';
import type { RunStatus } from '@/types';

export const RunStatusBadge: React.FC<{ status: RunStatus }> = ({ status }) => {
  const tone =
    status === 'completed'
      ? 'success'
      : status === 'running' || status === 'pending' || status === 'cancelling'
        ? 'primary'
        : status === 'cancelled' || status === 'interrupted'
          ? 'warning'
          : 'error';
  return <Badge tone={tone}>{status}</Badge>;
};

/** Tiny line chart of recent scores (oldest to newest, 0..1). */
export const Sparkline: React.FC<{ values: number[]; width?: number; height?: number }> = ({
  values,
  width = 96,
  height = 28,
}) => {
  if (values.length < 2) return <span className="text-xs text-muted-foreground">—</span>;
  const step = width / (values.length - 1);
  const points = values.map((v, i) => `${(i * step).toFixed(1)},${(height - 2 - v * (height - 4)).toFixed(1)}`);
  const last = values[values.length - 1];
  const first = values[0];
  return (
    <svg width={width} height={height} role="img" aria-label={`Score trend: ${values.map((v) => v.toFixed(2)).join(', ')}`}>
      <polyline
        points={points.join(' ')}
        fill="none"
        strokeWidth={2}
        strokeLinejoin="round"
        className={last >= first ? 'stroke-success' : 'stroke-error'}
      />
    </svg>
  );
};

/** Horizontal bar showing a confidence interval around zero. */
export const CIBar: React.FC<{ low: number; high: number; mean: number; significant: boolean }> = ({
  low,
  high,
  mean,
  significant,
}) => {
  const extent = Math.max(0.05, Math.abs(low), Math.abs(high)) * 1.15;
  const pos = (v: number) => `${((v + extent) / (2 * extent)) * 100}%`;
  const tone = !significant ? 'bg-muted-foreground/60' : mean > 0 ? 'bg-success' : 'bg-error';
  return (
    <div className="w-full">
      <div className="relative h-8 rounded-lg bg-white/[0.03]" role="img" aria-label={`95% interval from ${formatSigned(low)} to ${formatSigned(high)}`}>
        <div className="absolute inset-y-0 w-px bg-white/30" style={{ left: '50%' }} aria-hidden />
        <div
          className={cn('absolute top-1/2 h-2 -translate-y-1/2 rounded-full', tone)}
          style={{ left: pos(low), width: `calc(${pos(high)} - ${pos(low)})`, minWidth: 2 }}
        />
        <div className={cn('absolute top-1/2 h-4 w-1 -translate-x-1/2 -translate-y-1/2 rounded', tone)} style={{ left: pos(mean) }} />
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-muted-foreground">
        <span>{formatSigned(-extent, 2)}</span>
        <span>0</span>
        <span>{formatSigned(extent, 2)}</span>
      </div>
    </div>
  );
};

export const Progress: React.FC<{ done: number; total: number; failed?: number }> = ({ done, total, failed = 0 }) => {
  const pct = total ? Math.min(100, (done / total) * 100) : 0;
  const failedPct = total ? Math.min(100, (failed / total) * 100) : 0;
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-white/[0.05]" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
      <div className="flex h-full">
        <div className="h-full bg-primary transition-[width]" style={{ width: `${pct - failedPct}%` }} />
        <div className="h-full bg-error transition-[width]" style={{ width: `${failedPct}%` }} />
      </div>
    </div>
  );
};
