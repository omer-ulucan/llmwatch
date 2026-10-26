/**
 * A KPI tile. The trend shows a real period-over-period change when one is passed,
 * and nothing otherwise (no invented numbers).
 */
import React from 'react';
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';
import { cn } from '@/lib/cn';
import { formatSignedPct } from '@/lib/format';
import { Skeleton } from './feedback';

interface StatCardProps {
  title: string;
  value: React.ReactNode;
  icon?: React.ReactNode;
  /** Percent change versus the previous period; null/undefined hides it. */
  deltaPct?: number | null;
  /** True when going up is bad (cost, latency, errors). */
  inverse?: boolean;
  hint?: React.ReactNode;
  loading?: boolean;
}

export const StatCard: React.FC<StatCardProps> = ({ title, value, icon, deltaPct, inverse = false, hint, loading }) => {
  const hasDelta = deltaPct !== null && deltaPct !== undefined && !Number.isNaN(deltaPct);
  const flat = hasDelta && Math.abs(deltaPct) < 0.05;
  const up = hasDelta && deltaPct > 0;
  const good = flat ? null : inverse ? !up : up;
  return (
    <div className="glass-card rounded-2xl p-5 w-full">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-medium text-muted-foreground tracking-wide uppercase">{title}</h3>
        {icon && <div className="rounded-xl bg-white/[0.03] p-2 text-primary">{icon}</div>}
      </div>
      {loading ? (
        <Skeleton className="h-8 w-24" />
      ) : (
        <div className="text-2xl font-bold tracking-tight sm:text-3xl">{value}</div>
      )}
      <div className="mt-2 flex min-h-5 items-center gap-2 text-xs">
        {hasDelta && !loading && (
          <span
            className={cn(
              'inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 font-medium',
              good === null ? 'bg-white/[0.05] text-muted-foreground' : good ? 'bg-success-bg text-success' : 'bg-error-bg text-error',
            )}
            title="Change versus the previous period of the same length"
          >
            {flat ? <Minus size={12} /> : up ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
            {formatSignedPct(deltaPct)}
          </span>
        )}
        {hint && <span className="text-muted-foreground">{hint}</span>}
      </div>
    </div>
  );
};
