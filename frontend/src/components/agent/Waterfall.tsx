/**
 * Component: Waterfall
 * Purpose: The steps of an agent run as a timeline with latency bars.
 * WHY: Shows where time and money went: each model call and tool call is a row whose
 * bar is proportional to its latency, with token and cost figures; tool inputs and
 * outputs expand inline. Used for live runs and stored traces alike.
 */
import React, { useState } from 'react';
import {
  AlertCircle,
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  PlayCircle,
  Wrench,
  type LucideIcon,
} from 'lucide-react';
import { Markdown } from '@/components/chat/Markdown';
import { Badge } from '@/components/ui';
import { cn } from '@/lib/cn';
import { formatCost, formatMs, formatNumber } from '@/lib/format';
import type { AgentEvent, AgentRunSummary } from '@/types';

const STYLE: Record<
  AgentEvent['event_type'],
  { icon: LucideIcon; label: string; bar: string; text: string }
> = {
  run_start: { icon: PlayCircle, label: 'Start', bar: 'bg-white/20', text: 'text-muted-foreground' },
  thinking: { icon: BrainCircuit, label: 'Model call', bar: 'bg-secondary', text: 'text-secondary' },
  tool_call: { icon: Wrench, label: 'Tool call', bar: 'bg-warning', text: 'text-warning' },
  tool_result: { icon: Wrench, label: 'Tool result', bar: 'bg-warning', text: 'text-warning' },
  final_answer: { icon: CheckCircle2, label: 'Answer', bar: 'bg-success', text: 'text-success' },
  error: { icon: AlertCircle, label: 'Error', bar: 'bg-error', text: 'text-error' },
  run_end: { icon: CheckCircle2, label: 'End', bar: 'bg-white/20', text: 'text-muted-foreground' },
};

function prettyJson(raw: string | undefined): string {
  if (!raw) return '';
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

const StepRow: React.FC<{ step: AgentEvent; maxLatency: number }> = ({ step, maxLatency }) => {
  const style = STYLE[step.event_type];
  const Icon = style.icon;
  const expandable = step.event_type !== 'run_start' && step.event_type !== 'final_answer';
  const [open, setOpen] = useState(step.event_type === 'error');
  const width = step.latency_ms && maxLatency ? Math.max(2, (step.latency_ms / maxLatency) * 100) : 0;
  const title =
    step.event_type === 'tool_call' || step.event_type === 'tool_result'
      ? `${style.label}: ${step.tool_name ?? 'tool'}`
      : style.label;

  return (
    <li className="rounded-xl border border-card-border bg-card/40">
      <button
        type="button"
        onClick={() => expandable && setOpen(!open)}
        aria-expanded={expandable ? open : undefined}
        className={cn('flex w-full items-center gap-3 px-3 py-2.5 text-left', expandable && 'cursor-pointer')}
      >
        <Icon size={16} className={cn('shrink-0', style.text)} aria-hidden />
        <span className="w-40 shrink-0 truncate text-sm font-medium sm:w-48">
          {title}
          {step.is_error && <Badge tone="error" className="ml-2">error</Badge>}
        </span>
        <span className="relative hidden h-2 flex-1 overflow-hidden rounded-full bg-white/[0.04] sm:block" aria-hidden>
          {width > 0 && <span className={cn('absolute inset-y-0 left-0 rounded-full', style.bar)} style={{ width: `${width}%` }} />}
        </span>
        <span className="ml-auto flex shrink-0 gap-3 text-xs text-muted-foreground tabular-nums sm:ml-0">
          {step.latency_ms !== undefined && <span>{formatMs(step.latency_ms)}</span>}
          {step.tokens ? <span>{formatNumber(step.tokens)} tok</span> : null}
          {step.cost_usd ? <span>{formatCost(step.cost_usd)}</span> : null}
        </span>
        {expandable && <ChevronRight size={14} className={cn('shrink-0 text-muted-foreground transition-transform', open && 'rotate-90')} />}
      </button>
      {step.event_type === 'final_answer' && (
        <div className="border-t border-card-border px-4 py-3">
          <Markdown>{step.content}</Markdown>
        </div>
      )}
      {expandable && open && (
        <div className="space-y-2 border-t border-card-border px-4 py-3 text-sm">
          {step.tool_input && (
            <div>
              <div className="mb-1 text-xs uppercase tracking-wider text-muted-foreground">Input</div>
              <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg bg-black/30 p-3 text-xs">{prettyJson(step.tool_input)}</pre>
            </div>
          )}
          {step.event_type !== 'tool_call' && (
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-black/30 p-3 text-xs text-muted-foreground">
              {step.content}
            </pre>
          )}
        </div>
      )}
    </li>
  );
};

export const Waterfall: React.FC<{ steps: AgentEvent[] }> = ({ steps }) => {
  const visible = steps.filter((s) => s.event_type !== 'run_end');
  const maxLatency = Math.max(0, ...visible.map((s) => s.latency_ms ?? 0));
  return (
    <ol className="space-y-2" aria-label="Agent steps">
      {visible.map((step) => (
        <StepRow key={`${step.run_id}-${step.step_index}`} step={step} maxLatency={maxLatency} />
      ))}
    </ol>
  );
};

export const RunSummary: React.FC<{ summary: AgentRunSummary }> = ({ summary }) => {
  const status = summary.status ?? (summary.success ? 'success' : 'error');
  const items = [
    { label: 'Status', value: <Badge tone={status === 'success' ? 'success' : status === 'cancelled' ? 'warning' : 'error'}>{status}</Badge> },
    { label: 'Total time', value: formatMs(summary.total_latency_ms) },
    { label: 'Model calls', value: summary.llm_calls ?? '—' },
    { label: 'Tokens', value: formatNumber(summary.total_tokens) },
    { label: 'Cost', value: summary.priced === false ? 'unpriced' : formatCost(summary.total_cost_usd) },
    { label: 'Tools used', value: summary.tools_used.length ? summary.tools_used.join(', ') : 'none' },
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 rounded-2xl border border-card-border bg-card/40 p-4 sm:grid-cols-3 lg:grid-cols-6">
      {items.map((i) => (
        <div key={i.label}>
          <dt className="text-xs uppercase tracking-wider text-muted-foreground">{i.label}</dt>
          <dd className="mt-1 text-sm font-medium">{i.value}</dd>
        </div>
      ))}
    </dl>
  );
};
