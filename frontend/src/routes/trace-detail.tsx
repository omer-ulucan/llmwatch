/**
 * Component: TraceDetail
 * Purpose: One stored agent run: task, outcome, totals and the step waterfall.
 */
import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router';
import { ArrowLeft } from 'lucide-react';
import { agentApi } from '@/api/agent';
import { RunSummary, Waterfall } from '@/components/agent/Waterfall';
import { Markdown } from '@/components/chat/Markdown';
import { Card, ErrorState, PageHeader, SkeletonRows } from '@/components/ui';
import { formatDateTime } from '@/lib/format';
import type { AgentRunSummary } from '@/types';

const TraceDetail: React.FC = () => {
  const { runId = '' } = useParams();
  const { data: trace, isLoading, error, refetch } = useQuery({
    queryKey: ['trace', runId],
    queryFn: () => agentApi.getTrace(runId).then((r) => r.data.trace),
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 2000 : false),
  });

  if (isLoading) return <SkeletonRows rows={8} className="mx-auto max-w-5xl" />;
  if (error || !trace) return <ErrorState error={error} onRetry={() => void refetch()} />;

  const summary: AgentRunSummary = {
    run_id: trace.run_id,
    total_steps: trace.total_steps,
    total_latency_ms: trace.total_latency_ms,
    total_tokens: trace.total_tokens,
    total_cost_usd: trace.total_cost_usd,
    tools_used: trace.tools_used,
    model_used: trace.model_used,
    success: trace.success,
    status: trace.status === 'running' ? undefined : trace.status,
  };

  return (
    <div className="mx-auto max-w-5xl space-y-5 pb-12">
      <Link to="/traces" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft size={14} /> All traces
      </Link>
      <PageHeader title="Agent run" description={`${trace.model_used} · ${formatDateTime(trace.timestamp)}`} />
      <Card className="p-5">
        <div className="text-xs uppercase tracking-wider text-muted-foreground">Task</div>
        <p className="mt-1 whitespace-pre-wrap">{trace.prompt}</p>
      </Card>
      {trace.status === 'running' ? (
        <p className="text-sm text-muted-foreground">This run is still in progress…</p>
      ) : (
        <RunSummary summary={summary} />
      )}
      {trace.error && (
        <p className="rounded-xl border border-error/30 bg-error/10 px-4 py-3 text-sm text-error" role="alert">
          {trace.error}
        </p>
      )}
      {trace.final_answer && (
        <Card className="p-5">
          <div className="mb-2 text-xs uppercase tracking-wider text-muted-foreground">Final answer</div>
          <Markdown>{trace.final_answer}</Markdown>
        </Card>
      )}
      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">Steps</h2>
        <Waterfall steps={trace.steps ?? []} />
      </section>
    </div>
  );
};

export default TraceDetail;
