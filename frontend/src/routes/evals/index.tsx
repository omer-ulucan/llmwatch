/**
 * Component: Evals
 * Purpose: Every eval suite with its latest result and recent score trend.
 * WHY: The starting point for testing prompts and models: create or import a suite,
 * then open it to run and compare.
 */
import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { FileUp, FlaskConical, Plus } from 'lucide-react';
import { ImportDialog } from '@/components/evals/ImportDialog';
import { RunStatusBadge, Sparkline } from '@/components/evals/bits';
import { Button, Card, DataTable, EmptyState, ErrorState, PageHeader, type Column } from '@/components/ui';
import { useRuns, useSuites } from '@/hooks/useEvals';
import { STARTER_SUITE } from '@/lib/evals';
import { formatRatio, formatRelative } from '@/lib/format';
import type { EvalRun, SuiteSummary } from '@/types';

type Row = SuiteSummary & { runs: EvalRun[] };

const columns: Column<Row>[] = [
  {
    key: 'name',
    header: 'Suite',
    sortValue: (s) => s.name,
    render: (s) => (
      <div>
        <div className="font-medium">{s.name}</div>
        {s.description && <div className="line-clamp-1 max-w-md text-xs text-muted-foreground">{s.description}</div>}
      </div>
    ),
  },
  { key: 'version', header: 'Version', render: (s) => `v${s.latest_version}` },
  { key: 'cases', header: 'Cases', align: 'right', sortValue: (s) => s.case_count, render: (s) => s.case_count ?? '—' },
  {
    key: 'last',
    header: 'Last run',
    render: (s) => {
      const last = s.runs[0];
      if (!last) return <span className="text-muted-foreground">never</span>;
      return (
        <div className="flex items-center gap-2 whitespace-nowrap">
          <RunStatusBadge status={last.status} />
          <span className="text-xs text-muted-foreground">{last.label}</span>
        </div>
      );
    },
  },
  {
    key: 'pass',
    header: 'Pass rate',
    align: 'right',
    sortValue: (s) => s.runs.find((r) => r.status === 'completed')?.pass_rate ?? -1,
    render: (s) => formatRatio(s.runs.find((r) => r.status === 'completed')?.pass_rate),
  },
  {
    key: 'trend',
    header: 'Score trend',
    render: (s) => (
      <Sparkline
        values={s.runs
          .filter((r) => r.status === 'completed' && r.mean_score !== null)
          .slice(0, 12)
          .reverse()
          .map((r) => r.mean_score ?? 0)}
      />
    ),
  },
  { key: 'updated', header: 'Updated', sortValue: (s) => s.updated_at, render: (s) => <span className="text-muted-foreground">{formatRelative(s.updated_at)}</span> },
];

const Evals: React.FC = () => {
  const suites = useSuites();
  const runs = useRuns();
  const navigate = useNavigate();
  const [dialog, setDialog] = useState<'new' | 'import' | null>(null);

  const rows: Row[] = useMemo(() => {
    const bySuite = new Map<string, EvalRun[]>();
    // Runs arrive newest first.
    for (const run of runs.data ?? []) bySuite.set(run.suite_id, [...(bySuite.get(run.suite_id) ?? []), run]);
    return (suites.data ?? []).map((s) => ({ ...s, runs: bySuite.get(s.id) ?? [] }));
  }, [suites.data, runs.data]);

  return (
    <div className="mx-auto max-w-7xl pb-12">
      <PageHeader
        title="Evals"
        description="Test prompts and models against cases, then compare runs with confidence intervals."
        actions={
          <>
            <Button variant="secondary" onClick={() => setDialog('import')}>
              <FileUp size={16} /> Import
            </Button>
            <Button onClick={() => setDialog('new')}>
              <Plus size={16} /> New suite
            </Button>
          </>
        }
      />
      <Card className="overflow-hidden">
        {suites.error ? (
          <ErrorState error={suites.error} onRetry={() => void suites.refetch()} />
        ) : (
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(s) => s.id}
            loading={suites.isLoading}
            onRowClick={(s) => navigate(`/evals/suites/${s.id}`)}
            initialSort={{ key: 'updated', dir: 'desc' }}
            empty={
              <EmptyState
                icon={<FlaskConical size={28} />}
                title="No eval suites yet"
                description="A suite is a prompt template plus cases with assertions. Start from a template or import a YAML file."
                action={<Button onClick={() => setDialog('new')}>Create a suite</Button>}
              />
            }
          />
        )}
      </Card>
      {dialog && (
        <ImportDialog
          open
          onOpenChange={(open) => !open && setDialog(null)}
          initial={dialog === 'new' ? STARTER_SUITE : ''}
          title={dialog === 'new' ? 'New suite' : 'Import a suite'}
        />
      )}
    </div>
  );
};

export default Evals;
