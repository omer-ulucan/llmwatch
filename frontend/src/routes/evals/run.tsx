/**
 * Component: EvalRun
 * Purpose: One eval run: live progress, totals and per-case results.
 * WHY: Failures are what matter, so results filter by outcome and each one expands
 * to the model output and every evaluator's score and reason.
 */
import React, { useEffect, useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router';
import { AlertTriangle, ArrowLeft, ChevronRight, RotateCcw, Square, Trash2 } from 'lucide-react';
import { evalsApi } from '@/api/evals';
import { getErrorMessage } from '@/api/errors';
import { Progress, RunStatusBadge } from '@/components/evals/bits';
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, PageHeader, Skeleton, SkeletonRows, toast } from '@/components/ui';
import { useRun } from '@/hooks/useEvals';
import { cn } from '@/lib/cn';
import { costPerItem, isActiveStatus } from '@/lib/evals';
import { formatCost, formatDateTime, formatMs, formatNumber, formatRatio } from '@/lib/format';
import type { EvalResultItem } from '@/types';

const PAGE_SIZE = 25;
type Filter = 'all' | 'failed' | 'error' | 'passed';

const ResultRow: React.FC<{ item: EvalResultItem }> = ({ item }) => {
  const [open, setOpen] = useState(false);
  return (
    <li className="border-b border-card-border last:border-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-white/[0.02]"
      >
        <ChevronRight size={14} className={cn('shrink-0 text-muted-foreground transition-transform', open && 'rotate-90')} />
        <span className="w-40 shrink-0 truncate font-mono text-sm sm:w-56">
          {item.case_id}
          {item.repeat_index > 0 && <span className="text-muted-foreground"> #{item.repeat_index + 1}</span>}
        </span>
        {item.error ? <Badge tone="error">error</Badge> : item.passed ? <Badge tone="success">pass</Badge> : <Badge tone="warning">fail</Badge>}
        <span className="hidden min-w-0 flex-1 truncate text-sm text-muted-foreground md:block">{item.error ?? item.output}</span>
        <span className="ml-auto flex shrink-0 gap-3 text-xs tabular-nums text-muted-foreground">
          <span>{item.score.toFixed(2)}</span>
          <span className="hidden sm:inline">{formatMs(item.latency_ms)}</span>
          {item.cached && <span>cached</span>}
        </span>
      </button>
      {open && (
        <div className="space-y-3 px-4 pb-4 pl-11 text-sm">
          {Object.keys(item.vars).length > 0 && (
            <div className="font-mono text-xs text-muted-foreground">
              {Object.entries(item.vars)
                .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
                .join('  ')}
            </div>
          )}
          {item.error && <p className="rounded-xl border border-error/30 bg-error/10 p-3 text-error">{item.error}</p>}
          <div className="grid gap-3 lg:grid-cols-2">
            <div>
              <div className="mb-1 text-xs uppercase tracking-wider text-muted-foreground">Output</div>
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-xl bg-black/30 p-3 text-xs">{item.output || '—'}</pre>
            </div>
            {item.expected !== null && (
              <div>
                <div className="mb-1 text-xs uppercase tracking-wider text-muted-foreground">Expected</div>
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-xl bg-black/30 p-3 text-xs">{item.expected}</pre>
              </div>
            )}
          </div>
          {item.reasoning && (
            <details>
              <summary className="cursor-pointer text-xs text-muted-foreground">Reasoning</summary>
              <pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap rounded-xl bg-black/30 p-3 text-xs text-muted-foreground">
                {item.reasoning}
              </pre>
            </details>
          )}
          <table className="w-full text-left text-xs">
            <thead className="text-muted-foreground">
              <tr>
                <th className="py-1 font-medium">Evaluator</th>
                <th className="py-1 font-medium">Score</th>
                <th className="py-1 font-medium">Reason</th>
              </tr>
            </thead>
            <tbody>
              {item.evaluator_results.map((e, i) => (
                <tr key={i} className="border-t border-card-border align-top">
                  <td className="py-1.5 pr-3 font-mono">
                    {e.type}
                    {e.weight !== 1 && <span className="text-muted-foreground"> ×{e.weight}</span>}
                  </td>
                  <td className={cn('py-1.5 pr-3 tabular-nums', e.passed ? 'text-success' : 'text-error')}>{e.score.toFixed(2)}</td>
                  <td className="py-1.5">
                    {e.reason}
                    {e.warnings?.map((w) => (
                      <div key={w} className="mt-1 flex items-center gap-1 text-warning">
                        <AlertTriangle size={12} /> {w}
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
            <span>{formatNumber(item.input_tokens)} in / {formatNumber(item.output_tokens)} out tokens</span>
            <span>{formatCost(item.cost_usd)}</span>
            {item.tags.length > 0 && <span>tags: {item.tags.join(', ')}</span>}
          </div>
        </div>
      )}
    </li>
  );
};

const EvalRunPage: React.FC = () => {
  const { id = '' } = useParams();
  const run = useRun(id);
  const [filter, setFilter] = useState<Filter>('all');
  const [page, setPage] = useState(1);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const active = run.data ? isActiveStatus(run.data.status) : false;

  useEffect(() => setPage(1), [filter]);

  const results = useQuery({
    queryKey: ['eval-results', id, filter, page],
    queryFn: () => evalsApi.results(id, { status: filter === 'all' ? undefined : filter, page, page_size: PAGE_SIZE }),
    placeholderData: keepPreviousData,
    refetchInterval: active ? 2500 : false,
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['eval-run', id] });
    void queryClient.invalidateQueries({ queryKey: ['eval-runs'] });
  };
  const cancel = useMutation({
    mutationFn: () => evalsApi.cancel(id),
    onSuccess: refresh,
    onError: (err) => toast.error(getErrorMessage(err, 'Could not cancel')),
  });
  const resume = useMutation({
    mutationFn: (retryErrors: boolean) => evalsApi.resume(id, retryErrors),
    onSuccess: refresh,
    onError: (err) => toast.error(getErrorMessage(err, 'Could not resume')),
  });
  const remove = useMutation({
    mutationFn: () => evalsApi.removeRun(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['eval-runs'] });
      toast.success('Run deleted');
      navigate(run.data ? `/evals/suites/${run.data.suite_id}` : '/evals');
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Delete failed')),
  });

  if (run.error) return <ErrorState error={run.error} onRetry={() => void run.refetch()} />;
  if (!run.data) return <Skeleton className="h-64 w-full" />;
  const r = run.data;
  const resumable = r.status === 'cancelled' || r.status === 'interrupted' || r.status === 'failed';
  const totalPages = Math.max(1, Math.ceil((results.data?.total ?? 0) / PAGE_SIZE));

  const stats = [
    { label: 'Mean score', value: r.mean_score?.toFixed(3) ?? '—' },
    { label: 'Pass rate', value: formatRatio(r.pass_rate) },
    { label: 'Errors', value: formatNumber(r.failed_items) },
    { label: 'Cost / case', value: r.pricing_snapshot.input_price_per_mtok === null ? 'unpriced' : formatCost(costPerItem(r)) },
    { label: 'Total cost', value: formatCost(r.total_cost_usd) },
    { label: 'Tokens', value: formatNumber(r.total_tokens) },
  ];

  return (
    <div className="mx-auto max-w-7xl space-y-4 pb-12">
      <Link to={`/evals/suites/${r.suite_id}`} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft size={14} /> Back to suite
      </Link>
      <PageHeader
        title={r.label}
        description={`${r.variant.provider} · started ${formatDateTime(r.started_at ?? r.created_at)}${r.repeats > 1 ? ` · ${r.repeats} repeats` : ''}${r.variant.thinking ? ' · thinking on' : ''}`}
        actions={
          <>
            {active && (
              <Button variant="danger" onClick={() => cancel.mutate()} loading={cancel.isPending} disabled={r.status === 'cancelling'}>
                <Square size={16} /> Cancel
              </Button>
            )}
            {resumable && (
              <Button variant="secondary" onClick={() => resume.mutate(r.failed_items > 0)} loading={resume.isPending}>
                <RotateCcw size={16} /> {r.failed_items > 0 ? 'Resume and retry errors' : 'Resume'}
              </Button>
            )}
            {!active && (
              <Button variant="ghost" aria-label="Delete run" onClick={() => setConfirmDelete(true)}>
                <Trash2 size={16} />
              </Button>
            )}
          </>
        }
      />
      <Card className="space-y-4 p-5">
        <div className="flex flex-wrap items-center gap-3">
          <RunStatusBadge status={r.status} />
          <span className="text-sm text-muted-foreground">
            {formatNumber(r.completed_items)} / {formatNumber(r.total_items)} items
          </span>
        </div>
        <Progress done={r.completed_items} total={r.total_items} failed={r.failed_items} />
        {r.error && <p className="text-sm text-error">{r.error}</p>}
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {stats.map((s) => (
            <div key={s.label}>
              <dt className="text-xs uppercase tracking-wider text-muted-foreground">{s.label}</dt>
              <dd className="mt-1 text-lg font-semibold">{s.value}</dd>
            </div>
          ))}
        </dl>
      </Card>

      <Card className="overflow-hidden">
        <div className="flex flex-wrap gap-1 border-b border-card-border p-3" role="tablist" aria-label="Filter results">
          {(['all', 'failed', 'error', 'passed'] as Filter[]).map((f) => (
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
              {f === 'error' ? 'errors' : f}
            </button>
          ))}
        </div>
        {results.error ? (
          <ErrorState error={results.error} onRetry={() => void results.refetch()} />
        ) : results.isLoading ? (
          <SkeletonRows rows={6} />
        ) : results.data && results.data.items.length > 0 ? (
          <>
            <ul>
              {results.data.items.map((item) => (
                <ResultRow key={item.id} item={item} />
              ))}
            </ul>
            {totalPages > 1 && (
              <div className="flex items-center justify-end gap-2 border-t border-card-border px-4 py-3 text-sm text-muted-foreground">
                <span>
                  Page {page} of {totalPages}
                </span>
                <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                  Previous
                </Button>
                <Button size="sm" variant="secondary" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
                  Next
                </Button>
              </div>
            )}
          </>
        ) : (
          <EmptyState title={active ? 'Waiting for results…' : filter === 'all' ? 'No results' : `No ${filter === 'error' ? 'errors' : filter} results`} />
        )}
      </Card>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this run?"
        description="Its results are deleted too. Comparisons that used it will no longer open."
        confirmLabel="Delete run"
        danger
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </div>
  );
};

export default EvalRunPage;
