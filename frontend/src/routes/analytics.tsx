/**
 * Component: Analytics
 * Purpose: The raw call log with filters, search and CSV export.
 * WHY: Engineers need to find specific calls (slow, failed, expensive) and take the
 * filtered set elsewhere. Filtering, paging and export all happen on the server, over
 * the selected time window.
 */
import React, { useEffect, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Download, ScrollText, Search } from 'lucide-react';
import { analyticsApi, type AnalyticsFilters } from '@/api/analytics';
import { getErrorMessage } from '@/api/errors';
import { TimeRangePicker } from '@/components/analytics/TimeRange';
import { useTimeRange } from '@/hooks/useTimeRange';
import {
  Badge,
  Button,
  Card,
  DataTable,
  Dialog,
  EmptyState,
  ErrorState,
  Input,
  NativeSelect,
  PageHeader,
  toast,
  type Column,
} from '@/components/ui';
import { formatCost, formatDateTime, formatMs, formatNumber } from '@/lib/format';
import type { LogEntry } from '@/types';

const PAGE_SIZE = 50;

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

const StatusCell: React.FC<{ log: LogEntry }> = ({ log }) =>
  log.success ? (
    <Badge tone="success">ok</Badge>
  ) : log.error_type === 'cancelled' ? (
    <Badge tone="warning">cancelled</Badge>
  ) : (
    <Badge tone="error" title={log.error_message ?? undefined}>
      {log.error_type}
    </Badge>
  );

const columns: Column<LogEntry>[] = [
  { key: 'time', header: 'Time', render: (l) => <span className="whitespace-nowrap text-muted-foreground">{formatDateTime(l.timestamp)}</span> },
  {
    key: 'model',
    header: 'Model',
    render: (l) => (
      <div className="whitespace-nowrap">
        <div className="text-sm">{l.model_name}</div>
        <div className="text-xs text-muted-foreground">
          {l.provider_name ?? '—'} · {l.source}
        </div>
      </div>
    ),
  },
  { key: 'prompt', header: 'Prompt', render: (l) => <span className="line-clamp-2 max-w-sm text-sm">{l.prompt_preview || '—'}</span> },
  { key: 'status', header: 'Status', render: (l) => <StatusCell log={l} /> },
  { key: 'latency', header: 'Latency', align: 'right', render: (l) => formatMs(l.latency_ms) },
  { key: 'tokens', header: 'Tokens', align: 'right', render: (l) => formatNumber(l.input_tokens + l.output_tokens) },
  { key: 'cost', header: 'Cost', align: 'right', render: (l) => formatCost(l.cost_usd) },
];

const LogDialog: React.FC<{ log: LogEntry | null; onClose: () => void }> = ({ log, onClose }) => (
  <Dialog open={Boolean(log)} onOpenChange={(open) => !open && onClose()} title="Call details" className="max-w-2xl">
    {log && (
      <div className="space-y-4 text-sm">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ['Model', log.model_name],
            ['Provider', log.provider_name ?? '—'],
            ['Source', log.source],
            ['Status', log.success ? 'ok' : log.error_type],
            ['Latency', formatMs(log.latency_ms)],
            ['Input tokens', formatNumber(log.input_tokens)],
            ['Output tokens', formatNumber(log.output_tokens)],
            ['Cost', formatCost(log.cost_usd)],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs text-muted-foreground">{label}</dt>
              <dd className="font-medium">{value}</dd>
            </div>
          ))}
        </dl>
        {log.error_message && (
          <div className="rounded-xl border border-error/30 bg-error/10 p-3 text-error">
            {log.status_code ? `HTTP ${log.status_code}: ` : ''}
            {log.error_message}
          </div>
        )}
        <div>
          <div className="mb-1 text-xs uppercase tracking-wider text-muted-foreground">Prompt (preview)</div>
          <pre className="whitespace-pre-wrap rounded-xl bg-black/30 p-3 text-xs">{log.prompt_preview || '—'}</pre>
        </div>
        <div>
          <div className="mb-1 text-xs uppercase tracking-wider text-muted-foreground">Response (preview)</div>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-xl bg-black/30 p-3 text-xs">
            {log.response_preview || '—'}
          </pre>
        </div>
      </div>
    )}
  </Dialog>
);

const Analytics: React.FC = () => {
  const { range, setRange } = useTimeRange('24h');
  const [model, setModel] = useState('');
  const [provider, setProvider] = useState('');
  const [status, setStatus] = useState<AnalyticsFilters['status'] | ''>('');
  const [source, setSource] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<LogEntry | null>(null);
  const [exporting, setExporting] = useState(false);
  const q = useDebounced(search);

  const filters: AnalyticsFilters = {
    hours: range.hours,
    model: model || undefined,
    provider: provider || undefined,
    status: status || undefined,
    source: source || undefined,
    q: q || undefined,
  };
  const filterKey = JSON.stringify(filters);
  // Back to page 1 whenever the filters change.
  useEffect(() => setPage(1), [filterKey]);

  const options = useQuery({ queryKey: ['log-filters', range.hours], queryFn: () => analyticsApi.filters(range.hours) });
  const logs = useQuery({
    queryKey: ['logs', filters, page],
    queryFn: () => analyticsApi.logs({ ...filters, page, page_size: PAGE_SIZE }),
    placeholderData: keepPreviousData,
  });

  const exportCsv = async () => {
    setExporting(true);
    try {
      await analyticsApi.exportCsv(filters);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Export failed'));
    } finally {
      setExporting(false);
    }
  };

  const filtered = Boolean(model || provider || status || source || q);

  return (
    <div className="mx-auto max-w-7xl pb-12">
      <PageHeader
        title="Analytics"
        description="Every LLM call, filterable, with CSV export of the filtered set."
        actions={
          <>
            <TimeRangePicker value={range.id} onChange={setRange} />
            <Button variant="secondary" onClick={() => void exportCsv()} loading={exporting} disabled={!logs.data?.total}>
              <Download size={16} /> Export CSV
            </Button>
          </>
        }
      />
      <Card className="overflow-hidden">
        <div className="grid grid-cols-1 gap-2 border-b border-card-border p-4 sm:grid-cols-2 lg:grid-cols-5">
          <div className="relative sm:col-span-2 lg:col-span-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input className="pl-9" placeholder="Search prompts, responses, errors" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search" />
          </div>
          <NativeSelect value={model} onChange={(e) => setModel(e.target.value)} aria-label="Model">
            <option value="">All models</option>
            {options.data?.models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect value={provider} onChange={(e) => setProvider(e.target.value)} aria-label="Provider">
            <option value="">All providers</option>
            {options.data?.providers.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect value={status} onChange={(e) => setStatus(e.target.value as AnalyticsFilters['status'] | '')} aria-label="Status">
            <option value="">Any status</option>
            <option value="success">Success</option>
            <option value="error">Error</option>
            <option value="cancelled">Cancelled</option>
          </NativeSelect>
          <NativeSelect value={source} onChange={(e) => setSource(e.target.value)} aria-label="Source">
            <option value="">Any source</option>
            <option value="chat">Chat</option>
            <option value="agent">Agent</option>
            <option value="eval">Eval</option>
          </NativeSelect>
        </div>
        {logs.error ? (
          <ErrorState error={logs.error} onRetry={() => void logs.refetch()} />
        ) : (
          <DataTable
            columns={columns}
            rows={logs.data?.items ?? []}
            rowKey={(l) => l.log_id}
            loading={logs.isLoading}
            onRowClick={setSelected}
            pagination={{ page, pageSize: PAGE_SIZE, total: logs.data?.total ?? 0, onPageChange: setPage }}
            empty={
              <EmptyState
                icon={<ScrollText size={28} />}
                title={filtered ? 'No calls match these filters' : `No calls in the last ${range.label}`}
              />
            }
          />
        )}
      </Card>
      <LogDialog log={selected} onClose={() => setSelected(null)} />
    </div>
  );
};

export default Analytics;
