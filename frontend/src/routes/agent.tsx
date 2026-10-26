/**
 * Component: Agent
 * Purpose: Run the tool-using agent and watch its steps live.
 * WHY: Each model call and tool call appears as it happens, with latency, tokens and
 * cost, and the finished run is stored as a trace.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { Bot, ListTree, Play, RotateCcw, SlidersHorizontal, Square } from 'lucide-react';
import { agentApi } from '@/api/agent';
import { RunSummary, Waterfall } from '@/components/agent/Waterfall';
import { ModelPicker } from '@/components/models/ModelPicker';
import { Button, EmptyState, Field, Input, Sheet, Textarea } from '@/components/ui';
import { useAgentStream } from '@/hooks/useAgentStream';
import { useAvailableModels, useInitialModel } from '@/hooks/useModels';
import { cn } from '@/lib/cn';

interface AgentSettings {
  model: string;
  tools: string[];
  maxIterations: number;
}

const ToolsField: React.FC<{ selected: string[]; onChange: (tools: string[]) => void }> = ({ selected, onChange }) => {
  const { data, isLoading } = useQuery({
    queryKey: ['agent-tools'],
    queryFn: () => agentApi.getTools().then((r) => r.data.details),
    staleTime: 5 * 60_000,
  });
  if (isLoading) return <p className="text-sm text-muted-foreground">Loading tools…</p>;
  return (
    <fieldset className="space-y-2">
      <legend className="mb-2 text-sm font-medium">Tools</legend>
      {(data ?? []).map((tool) => {
        const on = selected.includes(tool.name);
        return (
          <label
            key={tool.name}
            className={cn(
              'flex cursor-pointer gap-3 rounded-xl border p-3 transition-colors',
              on ? 'border-primary/40 bg-primary/[0.06]' : 'border-card-border hover:bg-white/[0.02]',
            )}
          >
            <input
              type="checkbox"
              className="mt-1"
              checked={on}
              onChange={(e) => onChange(e.target.checked ? [...selected, tool.name] : selected.filter((t) => t !== tool.name))}
            />
            <span>
              <span className="block font-mono text-sm">{tool.name}</span>
              <span className="block text-xs text-muted-foreground">{tool.description}</span>
            </span>
          </label>
        );
      })}
      {data && !data.some((t) => t.name === 'python') && (
        <p className="text-xs text-muted-foreground">Python is disabled on this server (ENABLE_CODE_EXECUTION).</p>
      )}
    </fieldset>
  );
};

const SettingsPanel: React.FC<{ settings: AgentSettings; onChange: (s: AgentSettings) => void }> = ({ settings, onChange }) => {
  const { models } = useAvailableModels();
  const model = models.find((m) => m.id === settings.model);
  return (
    <div className="space-y-5">
      <Field
        label="Model"
        htmlFor="agent-model"
        hint={
          model && !model.capabilities.tools
            ? 'This model isn\'t marked as supporting tool calling; set it on the Models page if it does.'
            : undefined
        }
      >
        <ModelPicker id="agent-model" value={settings.model} onChange={(m) => onChange({ ...settings, model: m.id })} />
      </Field>
      <ToolsField selected={settings.tools} onChange={(tools) => onChange({ ...settings, tools })} />
      <Field label="Max steps" htmlFor="agent-steps" hint="Model calls before the run stops (1-20)">
        <Input
          id="agent-steps"
          type="number"
          min={1}
          max={20}
          value={settings.maxIterations}
          onChange={(e) => onChange({ ...settings, maxIterations: Math.min(20, Math.max(1, Number(e.target.value) || 1)) })}
        />
      </Field>
    </div>
  );
};

const Agent: React.FC = () => {
  const [prompt, setPrompt] = useState('');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settings, setSettings] = useState<AgentSettings>({ model: '', tools: [], maxIterations: 8 });
  const { steps, summary, running, error, run, stop, reset } = useAgentStream();

  const setModel = useCallback((id: string) => setSettings((s) => ({ ...s, model: id })), []);
  useInitialModel(settings.model, setModel);

  // Select every available tool once they load.
  const { data: tools } = useQuery({
    queryKey: ['agent-tools'],
    queryFn: () => agentApi.getTools().then((r) => r.data.details),
    staleTime: 5 * 60_000,
  });
  useEffect(() => {
    if (tools) setSettings((s) => (s.tools.length ? s : { ...s, tools: tools.map((t) => t.name) }));
  }, [tools]);

  const start = () => {
    if (!prompt.trim() || !settings.model || running) return;
    void run({ prompt: prompt.trim(), model: settings.model, tools: settings.tools, max_iterations: settings.maxIterations });
  };

  return (
    <div className="-m-4 flex h-[calc(100%+2rem)] sm:-m-6 sm:h-[calc(100%+3rem)] lg:-m-8 lg:h-[calc(100%+4rem)]">
      <aside className="hidden w-80 shrink-0 overflow-y-auto border-r border-border bg-card/40 p-6 lg:block">
        <h2 className="mb-5 text-sm font-semibold uppercase tracking-wider text-muted-foreground">Agent settings</h2>
        <SettingsPanel settings={settings} onChange={setSettings} />
      </aside>
      <Sheet open={settingsOpen} onOpenChange={setSettingsOpen} title="Agent settings">
        <SettingsPanel settings={settings} onChange={setSettings} />
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="border-b border-border p-4 sm:p-6">
          <div className="mx-auto max-w-4xl space-y-3">
            <Textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) start();
              }}
              rows={3}
              placeholder="Give the agent a task, e.g. “How much did I spend on LLM calls in the last 24 hours, by model?”"
              aria-label="Task"
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="ghost" size="sm" className="lg:hidden" onClick={() => setSettingsOpen(true)}>
                <SlidersHorizontal size={16} /> Settings
              </Button>
              <span className="hidden text-xs text-muted-foreground sm:inline">Ctrl/⌘ + Enter to run</span>
              <div className="flex-1" />
              {(steps.length > 0 || summary) && !running && (
                <Button variant="ghost" size="sm" onClick={reset}>
                  <RotateCcw size={16} /> Clear
                </Button>
              )}
              {running ? (
                <Button variant="danger" onClick={() => void stop()}>
                  <Square size={16} /> Stop
                </Button>
              ) : (
                <Button onClick={start} disabled={!prompt.trim() || !settings.model}>
                  <Play size={16} /> Run agent
                </Button>
              )}
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 sm:p-6" aria-live="polite">
          <div className="mx-auto max-w-4xl space-y-4">
            {summary && <RunSummary summary={summary} />}
            {error && !summary && (
              <p className="rounded-xl border border-error/30 bg-error/10 px-4 py-3 text-sm text-error" role="alert">
                {error}
              </p>
            )}
            {steps.length > 0 ? (
              <Waterfall steps={steps} />
            ) : running ? (
              <p className="text-sm text-muted-foreground">Starting…</p>
            ) : (
              <EmptyState
                icon={<Bot size={28} />}
                title="No run yet"
                description="Steps appear here as the agent works. Finished runs are saved as traces."
                action={
                  <Link to="/traces" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
                    <ListTree size={14} /> View traces
                  </Link>
                }
              />
            )}
            {summary && (
              <Link to={`/traces/${summary.run_id}`} className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
                <ListTree size={14} /> Open this trace
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Agent;
