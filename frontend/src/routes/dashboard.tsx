/**
 * Component: Dashboard
 * Purpose: Usage at a glance for the selected time window.
 * WHY: Every number comes from the database over the chosen window, and the trend
 * badges compare with the previous window of the same length (no invented trends).
 */
import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { Activity, AlertTriangle, Bot, Clock, DollarSign, MessageSquare } from 'lucide-react';
import { agentApi } from '@/api/agent';
import { analyticsApi } from '@/api/analytics';
import { SeriesChart } from '@/components/analytics/charts';
import { TimeRangePicker } from '@/components/analytics/TimeRange';
import { useTimeRange } from '@/hooks/useTimeRange';
import { Button, Card, DataTable, EmptyState, ErrorState, PageHeader, Skeleton, StatCard, type Column } from '@/components/ui';
import { formatCompact, formatCost, formatMs, formatNumber, formatPct } from '@/lib/format';
import type { ModelBreakdownEntry } from '@/types';

type ModelRow = ModelBreakdownEntry & { key: string };

const modelColumns: Column<ModelRow>[] = [
  {
    key: 'model',
    header: 'Model',
    sortValue: (m) => m.key,
    render: (m) => (
      <div>
        <div className="font-medium">{m.model}</div>
        {m.provider && <div className="text-xs text-muted-foreground">{m.provider}</div>}
      </div>
    ),
  },
  { key: 'requests', header: 'Requests', align: 'right', sortValue: (m) => m.requests, render: (m) => formatNumber(m.requests) },
  { key: 'errors', header: 'Error rate', align: 'right', sortValue: (m) => m.error_rate_pct, render: (m) => formatPct(m.error_rate_pct) },
  { key: 'latency', header: 'Avg latency', align: 'right', sortValue: (m) => m.avg_latency_ms, render: (m) => formatMs(m.avg_latency_ms) },
  {
    key: 'tokens',
    header: 'Tokens',
    align: 'right',
    sortValue: (m) => m.input_tokens + m.output_tokens,
    render: (m) => formatCompact(m.input_tokens + m.output_tokens),
  },
  { key: 'cost', header: 'Cost', align: 'right', sortValue: (m) => m.cost, render: (m) => formatCost(m.cost) },
];

const Dashboard: React.FC = () => {
  const { range, setRange } = useTimeRange('24h');
  const filters = { hours: range.hours };
  const summary = useQuery({ queryKey: ['summary', filters], queryFn: () => analyticsApi.summary(filters) });
  const series = useQuery({ queryKey: ['timeseries', filters], queryFn: () => analyticsApi.timeseries(filters) });
  const agent = useQuery({
    queryKey: ['agent-analytics', range.hours],
    queryFn: () => agentApi.getAgentAnalytics(range.hours).then((r) => r.data),
  });

  const s = summary.data;
  const models: ModelRow[] = Object.entries(s?.model_breakdown ?? {}).map(([key, m]) => ({ key, ...m }));
  const empty = s && s.total_requests === 0;

  return (
    <div className="mx-auto max-w-7xl space-y-6 pb-12">
      <PageHeader
        title="Dashboard"
        description={`LLM usage over the last ${range.label}, compared with the ${range.label} before.`}
        actions={<TimeRangePicker value={range.id} onChange={setRange} />}
      />

      {summary.error ? (
        <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            title="Requests"
            icon={<Activity size={20} />}
            loading={summary.isLoading}
            value={formatNumber(s?.total_requests)}
            deltaPct={s?.deltas_pct.total_requests}
          />
          <StatCard
            title="Cost"
            icon={<DollarSign size={20} />}
            loading={summary.isLoading}
            value={formatCost(s?.total_cost_usd)}
            deltaPct={s?.deltas_pct.total_cost_usd}
            inverse
            hint={s ? `${formatCompact(s.input_tokens + s.output_tokens)} tokens` : undefined}
          />
          <StatCard
            title="p95 latency"
            icon={<Clock size={20} />}
            loading={summary.isLoading}
            value={formatMs(s?.p95_latency_ms)}
            deltaPct={s?.deltas_pct.p95_latency_ms}
            inverse
            hint={s ? `p50 ${formatMs(s.p50_latency_ms)}` : undefined}
          />
          <StatCard
            title="Error rate"
            icon={<AlertTriangle size={20} />}
            loading={summary.isLoading}
            value={formatPct(s?.error_rate_pct)}
            deltaPct={s?.deltas_pct.error_rate_pct}
            inverse
            hint={s ? `${formatNumber(s.total_errors)} failed${s.total_cancelled ? `, ${s.total_cancelled} cancelled` : ''}` : undefined}
          />
        </div>
      )}

      {empty ? (
        <Card>
          <EmptyState
            icon={<MessageSquare size={28} />}
            title={`No LLM calls in the last ${range.label}`}
            description="Chat, agent runs and evals are all logged here with their latency, tokens and cost."
            action={
              <div className="flex flex-wrap justify-center gap-2">
                <Link to="/chat">
                  <Button>Open chat</Button>
                </Link>
                <Link to="/models">
                  <Button variant="secondary">Configure models</Button>
                </Link>
              </div>
            }
          />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card className="p-5">
              <h3 className="mb-4 font-semibold">Requests and errors</h3>
              {series.isLoading || !series.data ? (
                <Skeleton className="h-60 w-full" />
              ) : (
                <SeriesChart
                  buckets={series.data.buckets}
                  bucketSeconds={series.data.bucket_seconds}
                  series={[
                    { key: 'requests', label: 'Requests', color: 'var(--color-primary)' },
                    { key: 'errors', label: 'Errors', color: 'var(--color-error)' },
                  ]}
                  valueFormatter={(v) => formatCompact(v)}
                />
              )}
            </Card>
            <Card className="p-5">
              <h3 className="mb-4 font-semibold">Cost</h3>
              {series.isLoading || !series.data ? (
                <Skeleton className="h-60 w-full" />
              ) : (
                <SeriesChart
                  buckets={series.data.buckets}
                  bucketSeconds={series.data.bucket_seconds}
                  series={[{ key: 'cost_usd', label: 'Cost', color: 'var(--color-secondary)' }]}
                  valueFormatter={(v) => formatCost(v)}
                />
              )}
            </Card>
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <Card className="overflow-hidden xl:col-span-2">
              <h3 className="px-5 pt-5 font-semibold">By model</h3>
              <DataTable
                columns={modelColumns}
                rows={models}
                rowKey={(m) => m.key}
                loading={summary.isLoading}
                initialSort={{ key: 'requests', dir: 'desc' }}
                pageSize={8}
              />
            </Card>
            <Card className="p-5">
              <div className="mb-4 flex items-center gap-2">
                <Bot size={18} className="text-primary" />
                <h3 className="font-semibold">Agent runs</h3>
              </div>
              {agent.isLoading ? (
                <Skeleton className="h-32 w-full" />
              ) : agent.data && agent.data.total_runs > 0 ? (
                <dl className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <dt className="text-muted-foreground">Runs</dt>
                    <dd className="text-xl font-semibold">{formatNumber(agent.data.total_runs)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Success rate</dt>
                    <dd className="text-xl font-semibold">{formatPct(agent.data.success_rate)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Avg steps</dt>
                    <dd className="text-xl font-semibold">{agent.data.avg_steps}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Cost</dt>
                    <dd className="text-xl font-semibold">{formatCost(agent.data.total_cost_usd)}</dd>
                  </div>
                  {Object.keys(agent.data.tool_usage).length > 0 && (
                    <div className="col-span-2">
                      <dt className="mb-1 text-muted-foreground">Tools used</dt>
                      <dd className="flex flex-wrap gap-2">
                        {Object.entries(agent.data.tool_usage).map(([tool, n]) => (
                          <span key={tool} className="rounded-md bg-white/[0.05] px-2 py-0.5 font-mono text-xs">
                            {tool} × {n}
                          </span>
                        ))}
                      </dd>
                    </div>
                  )}
                </dl>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No agent runs in this window. <Link to="/agent" className="text-primary hover:underline">Run the agent</Link>
                </p>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
};

export default Dashboard;
