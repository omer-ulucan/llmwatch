/**
 * Component: Traces
 * Purpose: Stored agent runs, newest first; open one for its full timeline.
 */
import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { ListTree, Search } from 'lucide-react';
import { agentApi } from '@/api/agent';
import { Badge, Card, DataTable, EmptyState, ErrorState, Input, NativeSelect, PageHeader, type Column } from '@/components/ui';
import { formatCost, formatDateTime, formatMs, formatNumber, formatRelative } from '@/lib/format';
import type { AgentTrace } from '@/types';

export const StatusBadge: React.FC<{ status: AgentTrace['status'] }> = ({ status }) => (
  <Badge tone={status === 'success' ? 'success' : status === 'running' ? 'primary' : status === 'cancelled' ? 'warning' : 'error'}>
    {status}
  </Badge>
);

const Traces: React.FC = () => {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['traces'],
    queryFn: () => agentApi.getTraces(200).then((r) => r.data.traces),
    refetchInterval: (query) => (query.state.data?.some((t) => t.status === 'running') ? 3000 : false),
  });

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (data ?? []).filter(
      (t) =>
        (!status || t.status === status) &&
        (!needle || t.prompt.toLowerCase().includes(needle) || t.model_used.toLowerCase().includes(needle)),
    );
  }, [data, search, status]);

  const columns: Column<AgentTrace>[] = [
    {
      key: 'time',
      header: 'When',
      sortValue: (t) => t.timestamp,
      render: (t) => <span title={formatDateTime(t.timestamp)} className="whitespace-nowrap text-muted-foreground">{formatRelative(t.timestamp)}</span>,
    },
    { key: 'prompt', header: 'Task', render: (t) => <span className="line-clamp-2 max-w-md">{t.prompt}</span> },
    { key: 'model', header: 'Model', sortValue: (t) => t.model_used, render: (t) => <span className="whitespace-nowrap text-xs">{t.model_used}</span> },
    { key: 'status', header: 'Status', sortValue: (t) => t.status, render: (t) => <StatusBadge status={t.status} /> },
    { key: 'steps', header: 'Steps', align: 'right', sortValue: (t) => t.total_steps, render: (t) => t.total_steps },
    { key: 'latency', header: 'Time', align: 'right', sortValue: (t) => t.total_latency_ms, render: (t) => formatMs(t.total_latency_ms) },
    { key: 'tokens', header: 'Tokens', align: 'right', sortValue: (t) => t.total_tokens, render: (t) => formatNumber(t.total_tokens) },
    { key: 'cost', header: 'Cost', align: 'right', sortValue: (t) => t.total_cost_usd, render: (t) => formatCost(t.total_cost_usd) },
  ];

  return (
    <div className="mx-auto max-w-6xl pb-12">
      <PageHeader title="Traces" description="Every agent run with its steps, tokens and cost." />
      <Card className="overflow-hidden">
        <div className="flex flex-col gap-2 border-b border-card-border p-4 sm:flex-row">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input className="pl-9" placeholder="Search tasks or models" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search traces" />
          </div>
          <NativeSelect className="sm:w-44" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
            <option value="">All statuses</option>
            <option value="success">Success</option>
            <option value="error">Error</option>
            <option value="cancelled">Cancelled</option>
            <option value="running">Running</option>
          </NativeSelect>
        </div>
        {error ? (
          <ErrorState error={error} onRetry={() => void refetch()} />
        ) : (
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(t) => t.run_id}
            loading={isLoading}
            onRowClick={(t) => navigate(`/traces/${t.run_id}`)}
            initialSort={{ key: 'time', dir: 'desc' }}
            empty={
              <EmptyState
                icon={<ListTree size={28} />}
                title={data?.length ? 'No traces match' : 'No agent runs yet'}
                description={data?.length ? undefined : 'Run the agent and its trace appears here.'}
              />
            }
          />
        )}
      </Card>
    </div>
  );
};

export default Traces;
