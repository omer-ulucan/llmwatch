/**
 * Component: EvalCompare
 * Purpose: Baseline vs candidate run: is the difference real, and what does it cost?
 * WHY: Mean score deltas come with a paired-bootstrap 95% interval and pass-rate
 * changes with McNemar's test, so small or noisy differences are not reported as wins.
 * The server's warnings (few cases, different suite versions, unpriced models) are
 * shown as-is.
 */
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router';
import { AlertTriangle, ArrowLeft, ArrowRight, GitCompare } from 'lucide-react';
import { evalsApi } from '@/api/evals';
import { CIBar } from '@/components/evals/bits';
import { Badge, Card, DataTable, EmptyState, ErrorState, PageHeader, Skeleton, type Column } from '@/components/ui';
import { cn } from '@/lib/cn';
import { formatCost, formatMs, formatRatio, formatSigned, formatSignedPct } from '@/lib/format';
import type { CaseComparison, Comparison, RunInfo } from '@/types';

type ChangeFilter = 'all' | 'regressed' | 'fixed' | 'unchanged';

const VERDICT: Record<Comparison['verdict'], { label: string; className: string }> = {
  improved: { label: 'Candidate is better', className: 'border-success/30 bg-success/10 text-success' },
  regressed: { label: 'Candidate is worse', className: 'border-error/30 bg-error/10 text-error' },
  no_significant_difference: {
    label: 'No significant difference',
    className: 'border-card-border bg-white/[0.03] text-foreground',
  },
};

const RunCard: React.FC<{ role: string; run: RunInfo }> = ({ role, run }) => (
  <Link to={`/evals/runs/${run.id}`} className="block rounded-2xl border border-card-border bg-card/40 p-4 hover:bg-white/[0.03]">
    <div className="text-xs uppercase tracking-wider text-muted-foreground">{role}</div>
    <div className="mt-1 font-medium">{run.label}</div>
    <div className="mt-2 flex gap-4 text-sm text-muted-foreground">
      <span>score {run.mean_score?.toFixed(3) ?? '—'}</span>
      <span>pass {formatRatio(run.pass_rate)}</span>
    </div>
  </Link>
);

const caseColumns: Column<CaseComparison>[] = [
  { key: 'case', header: 'Case', sortValue: (c) => c.case_id, render: (c) => <span className="font-mono text-sm">{c.case_id}</span> },
  {
    key: 'change',
    header: 'Change',
    sortValue: (c) => c.change,
    render: (c) => (
      <Badge tone={c.change === 'regressed' ? 'error' : c.change === 'fixed' ? 'success' : 'neutral'}>{c.change}</Badge>
    ),
  },
  { key: 'base', header: 'Baseline', align: 'right', sortValue: (c) => c.baseline_score, render: (c) => c.baseline_score.toFixed(2) },
  { key: 'cand', header: 'Candidate', align: 'right', sortValue: (c) => c.candidate_score, render: (c) => c.candidate_score.toFixed(2) },
  {
    key: 'delta',
    header: 'Delta',
    align: 'right',
    sortValue: (c) => c.delta,
    render: (c) => (
      <span className={cn('tabular-nums', c.delta > 0 ? 'text-success' : c.delta < 0 ? 'text-error' : 'text-muted-foreground')}>
        {formatSigned(c.delta, 2)}
      </span>
    ),
  },
  {
    key: 'errors',
    header: 'Errors',
    align: 'right',
    render: (c) => (c.baseline_errors || c.candidate_errors ? `${c.baseline_errors} → ${c.candidate_errors}` : '—'),
  },
];

const Delta: React.FC<{ label: string; value: string; detail: string; good?: boolean | null }> = ({ label, value, detail, good }) => (
  <div>
    <dt className="text-xs uppercase tracking-wider text-muted-foreground">{label}</dt>
    <dd className={cn('mt-1 text-lg font-semibold', good === true && 'text-success', good === false && 'text-error')}>{value}</dd>
    <dd className="text-xs text-muted-foreground">{detail}</dd>
  </div>
);

const ComparisonView: React.FC<{ c: Comparison }> = ({ c }) => {
  const [filter, setFilter] = useState<ChangeFilter>('all');
  const verdict = VERDICT[c.verdict];
  const counts = {
    regressed: c.cases.filter((x) => x.change === 'regressed').length,
    fixed: c.cases.filter((x) => x.change === 'fixed').length,
    unchanged: c.cases.filter((x) => x.change === 'unchanged').length,
  };
  const rows = filter === 'all' ? c.cases : c.cases.filter((x) => x.change === filter);
  const priced = c.cost.baseline_priced && c.cost.candidate_priced;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-[1fr_auto_1fr] md:items-center">
        <RunCard role="Baseline" run={c.baseline} />
        <ArrowRight className="mx-auto hidden text-muted-foreground md:block" size={20} />
        <RunCard role="Candidate" run={c.candidate} />
      </div>

      <div className={cn('rounded-2xl border p-4', verdict.className)} role="status">
        <div className="text-lg font-semibold">{verdict.label}</div>
        <p className="mt-1 text-sm opacity-80">
          Over {c.paired_cases} paired cases. Significance uses a {Math.round(c.score.confidence * 100)}% paired bootstrap interval for
          the score and McNemar&apos;s test (α = {c.pass_rate.alpha}) for pass/fail.
        </p>
      </div>

      {c.warnings.length > 0 && (
        <ul className="space-y-1 rounded-2xl border border-warning/30 bg-warning/10 p-4 text-sm text-warning">
          {c.warnings.map((w) => (
            <li key={w} className="flex gap-2">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" /> {w}
            </li>
          ))}
        </ul>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-semibold">Mean score delta</h3>
            {c.score.significant ? <Badge tone={c.score.delta > 0 ? 'success' : 'error'}>significant</Badge> : <Badge>not significant</Badge>}
          </div>
          <div className="mb-3 text-2xl font-semibold tabular-nums">{formatSigned(c.score.delta)}</div>
          <CIBar low={c.score.ci_low} high={c.score.ci_high} mean={c.score.delta} significant={c.score.significant} />
          <p className="mt-2 text-xs text-muted-foreground">
            {Math.round(c.score.confidence * 100)}% interval [{formatSigned(c.score.ci_low)}, {formatSigned(c.score.ci_high)}] from{' '}
            {c.score.resamples.toLocaleString()} resamples. An interval that crosses 0 means no detectable difference.
          </p>
        </Card>
        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-semibold">Pass rate</h3>
            {c.pass_rate.significant ? (
              <Badge tone={c.pass_rate.delta > 0 ? 'success' : 'error'}>significant</Badge>
            ) : (
              <Badge>not significant</Badge>
            )}
          </div>
          <div className="mb-3 text-2xl font-semibold tabular-nums">
            {formatRatio(c.pass_rate.baseline)} → {formatRatio(c.pass_rate.candidate)}
          </div>
          <p className="text-sm text-muted-foreground">
            {c.pass_rate.fixes} fixed, {c.pass_rate.regressions} regressed.{' '}
            {c.pass_rate.test === 'none'
              ? 'No discordant cases, so there is nothing to test.'
              : `McNemar ${c.pass_rate.test === 'exact' ? 'exact binomial' : 'χ² with continuity correction'}: p = ${c.pass_rate.p_value.toPrecision(3)}.`}
          </p>
        </Card>
      </div>

      <Card className="p-5">
        <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Delta
            label="Cost per case"
            value={priced ? formatCost(c.cost.candidate_per_case) : 'unpriced'}
            detail={priced ? `${formatSignedPct(c.cost.delta_pct)} vs ${formatCost(c.cost.baseline_per_case)}` : 'Set model prices to compare cost'}
            good={priced && c.cost.delta_pct !== null ? c.cost.delta_per_case <= 0 : null}
          />
          <Delta
            label="Mean latency"
            value={formatMs(c.latency.candidate_mean_ms)}
            detail={`${formatSignedPct(c.latency.delta_pct)} vs ${formatMs(c.latency.baseline_mean_ms)}`}
            good={c.latency.delta_pct !== null ? c.latency.delta_ms <= 0 : null}
          />
          <Delta label="Regressed cases" value={String(counts.regressed)} detail="passed before, fail now" good={counts.regressed ? false : null} />
          <Delta label="Fixed cases" value={String(counts.fixed)} detail="failed before, pass now" good={counts.fixed ? true : null} />
        </dl>
      </Card>

      <Card className="overflow-hidden">
        <div className="flex flex-wrap gap-1 border-b border-card-border p-3" role="tablist" aria-label="Filter cases">
          {(['all', 'regressed', 'fixed', 'unchanged'] as ChangeFilter[]).map((f) => (
            <button
              key={f}
              role="tab"
              aria-selected={filter === f}
              onClick={() => setFilter(f)}
              className={cn(
                'rounded-lg px-3 py-1.5 text-sm capitalize',
                filter === f ? 'bg-white/[0.08] text-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {f} ({f === 'all' ? c.cases.length : counts[f]})
            </button>
          ))}
        </div>
        <DataTable
          columns={caseColumns}
          rows={rows}
          rowKey={(x) => x.case_id}
          pageSize={25}
          initialSort={{ key: 'delta', dir: 'asc' }}
          empty={<EmptyState title={`No ${filter} cases`} />}
        />
        {(c.baseline_only.length > 0 || c.candidate_only.length > 0) && (
          <p className="border-t border-card-border px-4 py-3 text-xs text-muted-foreground">
            Not paired (left out of the statistics):{' '}
            {[...c.baseline_only.map((x) => `${x} (baseline only)`), ...c.candidate_only.map((x) => `${x} (candidate only)`)].join(', ')}
          </p>
        )}
      </Card>
    </div>
  );
};

const EvalCompare: React.FC = () => {
  const [params] = useSearchParams();
  const baseline = params.get('baseline') ?? '';
  const candidate = params.get('candidate') ?? '';
  const comparison = useQuery({
    queryKey: ['eval-compare', baseline, candidate],
    queryFn: () => evalsApi.compare(baseline, candidate),
    enabled: Boolean(baseline && candidate),
  });

  return (
    <div className="mx-auto max-w-7xl pb-12">
      {comparison.data && (
        <Link
          to={`/evals/suites/${comparison.data.baseline.suite_id}`}
          className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft size={14} /> Back to suite
        </Link>
      )}
      <PageHeader title="Compare runs" description="Baseline against candidate, case by case." />
      {!baseline || !candidate ? (
        <Card>
          <EmptyState
            icon={<GitCompare size={28} />}
            title="Pick two runs"
            description="Open a suite, select two completed runs and choose Compare."
            action={
              <Link to="/evals" className="text-sm text-primary hover:underline">
                Go to evals
              </Link>
            }
          />
        </Card>
      ) : comparison.error ? (
        <ErrorState error={comparison.error} onRetry={() => void comparison.refetch()} />
      ) : comparison.data ? (
        <ComparisonView c={comparison.data} />
      ) : (
        <Skeleton className="h-96 w-full" />
      )}
    </div>
  );
};

export default EvalCompare;
