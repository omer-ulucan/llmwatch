/**
 * Component: Suite
 * Purpose: One eval suite: its runs, cases and YAML definition.
 * WHY: Run variants side by side, pick a baseline, and open comparisons. Editing the
 * definition saves a new immutable version, so earlier runs stay comparable.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router';
import { ArrowLeft, Download, GitCompare, Play, Star, Trash2 } from 'lucide-react';
import { parse as parseYaml, stringify as stringifyYaml } from 'yaml';
import { evalsApi } from '@/api/evals';
import { getErrorMessage } from '@/api/errors';
import { NewRunDialog } from '@/components/evals/NewRunDialog';
import { QualityCostChart } from '@/components/evals/QualityCostChart';
import { Progress, RunStatusBadge } from '@/components/evals/bits';
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  DataTable,
  EmptyState,
  ErrorState,
  NativeSelect,
  PageHeader,
  Skeleton,
  Textarea,
  toast,
  type Column,
} from '@/components/ui';
import { useRuns, useSuite } from '@/hooks/useEvals';
import { cn } from '@/lib/cn';
import { costPerItem, isActiveStatus } from '@/lib/evals';
import { formatCost, formatRatio, formatRelative } from '@/lib/format';
import type { CaseDoc, EvalRun, SuiteDetail, SuiteDocument } from '@/types';

type Tab = 'runs' | 'cases' | 'definition';

function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

const RunsTab: React.FC<{ suite: SuiteDetail }> = ({ suite }) => {
  const runs = useRuns(suite.id);
  const [selected, setSelected] = useState<string[]>([]);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const baseline = useMutation({
    mutationFn: (runId: string | null) => evalsApi.setBaseline(suite.id, runId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['eval-suite', suite.id] });
      void queryClient.invalidateQueries({ queryKey: ['eval-suites'] });
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Could not set the baseline')),
  });

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s.slice(-1), id]));

  const columns: Column<EvalRun>[] = [
    {
      key: 'select',
      header: <span className="sr-only">Select</span>,
      render: (r) => (
        <input
          type="checkbox"
          aria-label={`Select ${r.label}`}
          checked={selected.includes(r.id)}
          disabled={r.status !== 'completed'}
          onClick={(e) => e.stopPropagation()}
          onChange={() => toggle(r.id)}
        />
      ),
    },
    {
      key: 'label',
      header: 'Run',
      render: (r) => (
        <div className="min-w-48">
          <div className="flex items-center gap-2 font-medium">
            {r.label}
            {suite.baseline_run_id === r.id && <Badge tone="warning">baseline</Badge>}
          </div>
          <div className="text-xs text-muted-foreground">
            {r.variant.provider} · {formatRelative(r.created_at)}
            {r.repeats > 1 ? ` · ${r.repeats} repeats` : ''}
          </div>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (r) =>
        isActiveStatus(r.status) ? (
          <div className="w-32 space-y-1">
            <RunStatusBadge status={r.status} />
            <Progress done={r.completed_items} total={r.total_items} failed={r.failed_items} />
          </div>
        ) : (
          <RunStatusBadge status={r.status} />
        ),
    },
    { key: 'score', header: 'Mean score', align: 'right', sortValue: (r) => r.mean_score, render: (r) => r.mean_score?.toFixed(3) ?? '—' },
    { key: 'pass', header: 'Pass rate', align: 'right', sortValue: (r) => r.pass_rate, render: (r) => formatRatio(r.pass_rate) },
    { key: 'cost', header: 'Cost / case', align: 'right', sortValue: (r) => costPerItem(r), render: (r) => formatCost(costPerItem(r)) },
    {
      key: 'actions',
      header: <span className="sr-only">Actions</span>,
      align: 'right',
      render: (r) => (
        <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
          {r.status === 'completed' && suite.baseline_run_id && suite.baseline_run_id !== r.id && (
            <Link to={`/evals/compare?baseline=${suite.baseline_run_id}&candidate=${r.id}`}>
              <Button variant="ghost" size="sm" title="Compare with the baseline">
                <GitCompare size={14} />
              </Button>
            </Link>
          )}
          {r.status === 'completed' && (
            <Button
              variant="ghost"
              size="sm"
              title={suite.baseline_run_id === r.id ? 'Clear baseline' : 'Set as baseline'}
              aria-label={suite.baseline_run_id === r.id ? 'Clear baseline' : 'Set as baseline'}
              onClick={() => baseline.mutate(suite.baseline_run_id === r.id ? null : r.id)}
            >
              <Star size={14} className={cn(suite.baseline_run_id === r.id && 'fill-warning text-warning')} />
            </Button>
          )}
        </div>
      ),
    },
  ];

  const compareSelected = () => {
    const [a, b] = selected;
    // The baseline (or else the older run) is the reference side.
    const list = runs.data ?? [];
    const older = (x: string) => list.findIndex((r) => r.id === x);
    const [base, cand] = b === suite.baseline_run_id || (a !== suite.baseline_run_id && older(b) > older(a)) ? [b, a] : [a, b];
    navigate(`/evals/compare?baseline=${base}&candidate=${cand}`);
  };

  if (runs.error) return <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />;

  return (
    <div className="space-y-4">
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-card-border px-4 py-3 text-sm text-muted-foreground">
          <span>Select two completed runs to compare.</span>
          <div className="flex-1" />
          <Button size="sm" variant="secondary" disabled={selected.length !== 2} onClick={compareSelected}>
            <GitCompare size={14} /> Compare selected
          </Button>
        </div>
        <DataTable
          columns={columns}
          rows={runs.data ?? []}
          rowKey={(r) => r.id}
          loading={runs.isLoading}
          onRowClick={(r) => navigate(`/evals/runs/${r.id}`)}
          pageSize={15}
          empty={<EmptyState icon={<Play size={28} />} title="No runs yet" description="Start a run to score a model on this suite." />}
        />
      </Card>
      {(runs.data?.length ?? 0) > 0 && (
        <Card className="p-5">
          <h3 className="mb-4 font-semibold">Quality vs cost</h3>
          <QualityCostChart runs={runs.data ?? []} />
        </Card>
      )}
    </div>
  );
};

const CasesTab: React.FC<{ doc: SuiteDocument }> = ({ doc }) => {
  const columns: Column<CaseDoc>[] = [
    { key: 'id', header: 'Case', sortValue: (c) => c.id, render: (c) => <span className="font-mono text-sm">{c.id}</span> },
    {
      key: 'vars',
      header: 'Variables',
      render: (c) => (
        <span className="line-clamp-2 max-w-md font-mono text-xs text-muted-foreground">
          {Object.entries(c.vars)
            .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
            .join('  ')}
        </span>
      ),
    },
    { key: 'expected', header: 'Expected', render: (c) => <span className="line-clamp-2 max-w-xs text-sm">{c.expected ?? '—'}</span> },
    {
      key: 'assert',
      header: 'Assertions',
      render: (c) => (
        <div className="flex flex-wrap gap-1">
          {[...(doc.assert ?? []), ...(c.assert ?? [])].map((a, i) => (
            <Badge key={i}>{a.type}</Badge>
          ))}
        </div>
      ),
    },
    { key: 'tags', header: 'Tags', render: (c) => <span className="text-xs text-muted-foreground">{c.tags?.join(', ') || '—'}</span> },
  ];
  return (
    <Card className="overflow-hidden">
      <div className="space-y-2 border-b border-card-border p-4 text-sm">
        {doc.system_prompt && (
          <p>
            <span className="text-muted-foreground">System: </span>
            {doc.system_prompt}
          </p>
        )}
        <pre className="whitespace-pre-wrap rounded-xl bg-black/30 p-3 text-xs">{doc.prompt}</pre>
      </div>
      <DataTable columns={columns} rows={doc.cases} rowKey={(c) => c.id} pageSize={25} />
    </Card>
  );
};

const DefinitionTab: React.FC<{ suite: SuiteDetail; latest: boolean }> = ({ suite, latest }) => {
  const original = useMemo(() => stringifyYaml(suite.definition, { lineWidth: 0 }), [suite.definition]);
  const [text, setText] = useState(original);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  useEffect(() => setText(original), [original]);

  const save = useMutation({
    mutationFn: (doc: SuiteDocument) => evalsApi.update(suite.id, doc),
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: ['eval-suite', suite.id] });
      void queryClient.invalidateQueries({ queryKey: ['eval-suites'] });
      toast.success(saved.created_version ? `Saved as v${saved.version}` : 'No changes to save');
    },
    onError: (err) => setError(getErrorMessage(err, 'Save failed')),
  });

  const submit = () => {
    let doc: unknown;
    try {
      doc = parseYaml(text);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid YAML');
      return;
    }
    if (!doc || typeof doc !== 'object' || Array.isArray(doc)) {
      setError('The definition must be a YAML mapping with name, prompt and cases.');
      return;
    }
    save.mutate(doc as SuiteDocument);
  };

  return (
    <Card className="space-y-3 p-4">
      <p className="text-sm text-muted-foreground">
        {latest
          ? 'Saving creates a new version. Runs keep pointing at the version they ran.'
          : `You are viewing v${suite.version}. Saving creates a new latest version from this text.`}
      </p>
      <Textarea
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setError(null);
        }}
        rows={24}
        spellCheck={false}
        className="font-mono text-xs"
        aria-label="Suite YAML"
      />
      {error && (
        <p className="whitespace-pre-wrap text-sm text-error" role="alert">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" disabled={text === original} onClick={() => setText(original)}>
          Discard changes
        </Button>
        <Button onClick={submit} loading={save.isPending} disabled={text === original}>
          Save new version
        </Button>
      </div>
    </Card>
  );
};

const Suite: React.FC = () => {
  const { id = '' } = useParams();
  const [version, setVersion] = useState<number | undefined>();
  const suite = useSuite(id, version);
  const [tab, setTab] = useState<Tab>('runs');
  const [runOpen, setRunOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const remove = useMutation({
    mutationFn: () => evalsApi.remove(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['eval-suites'] });
      toast.success('Suite deleted');
      navigate('/evals');
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Delete failed')),
  });

  const exportYaml = async () => {
    try {
      const text = await evalsApi.exportText(id, 'yaml', version);
      download(`${suite.data?.name ?? 'suite'}.yaml`, text, 'application/yaml');
    } catch (err) {
      toast.error(getErrorMessage(err, 'Export failed'));
    }
  };

  if (suite.error) return <ErrorState error={suite.error} onRetry={() => void suite.refetch()} />;
  if (!suite.data) return <Skeleton className="h-64 w-full" />;
  const s = suite.data;

  return (
    <div className="mx-auto max-w-7xl pb-12">
      <Link to="/evals" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft size={14} /> All suites
      </Link>
      <PageHeader
        title={s.name}
        description={s.description || `${s.definition.cases.length} cases`}
        actions={
          <>
            <NativeSelect
              value={version ?? s.latest_version}
              onChange={(e) => {
                const v = Number(e.target.value);
                setVersion(v === s.latest_version ? undefined : v);
              }}
              aria-label="Version"
              className="w-auto"
            >
              {s.versions.map((v) => (
                <option key={v.version} value={v.version}>
                  v{v.version}
                  {v.version === s.latest_version ? ' (latest)' : ''}
                </option>
              ))}
            </NativeSelect>
            <Button variant="secondary" onClick={() => void exportYaml()} aria-label="Export YAML">
              <Download size={16} />
            </Button>
            <Button variant="danger" onClick={() => setConfirmDelete(true)} aria-label="Delete suite">
              <Trash2 size={16} />
            </Button>
            <Button onClick={() => setRunOpen(true)}>
              <Play size={16} /> New run
            </Button>
          </>
        }
      />
      <div className="mb-4 flex gap-1 border-b border-border" role="tablist">
        {(['runs', 'cases', 'definition'] as Tab[]).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={cn(
              '-mb-px border-b-2 px-4 py-2 text-sm capitalize transition-colors',
              tab === t ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t === 'cases' ? `Cases (${s.definition.cases.length})` : t}
          </button>
        ))}
      </div>
      {tab === 'runs' && <RunsTab suite={s} />}
      {tab === 'cases' && <CasesTab doc={s.definition} />}
      {tab === 'definition' && <DefinitionTab suite={s} latest={s.version === s.latest_version} />}

      {runOpen && <NewRunDialog open onOpenChange={setRunOpen} suiteId={s.id} version={version} />}
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete ${s.name}?`}
        description="This deletes every version, run and result of the suite. It cannot be undone."
        confirmLabel="Delete suite"
        danger
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </div>
  );
};

export default Suite;
