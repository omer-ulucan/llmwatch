/**
 * Component: Traces
 * Purpose: Agent trace list view with drill-down to trace detail timeline.
 * WHY: Provides observability into past agent executions. The list view shows summary
 * metrics, and clicking a trace expands/navigates to the full step-by-step timeline.
 * Uses the same AgentTimeline and AgentStepCard components as the live agent page.
 */
import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Clock, Hash, CheckCircle, XCircle, ChevronRight, ArrowLeft, Wrench, Search } from 'lucide-react';
import { agentApi } from '@/api/agent';
import AgentTimeline from '@/components/agent/AgentTimeline';
import type { AgentTrace, AgentEvent } from '@/types';

const Traces: React.FC = () => {
  const [traces, setTraces] = useState<AgentTrace[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTrace, setSelectedTrace] = useState<AgentTrace | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [search, setSearch] = useState('');

  useEffect(() => {
    agentApi.getTraces(100)
      .then(res => setTraces(res.data.traces))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleSelectTrace = async (trace: AgentTrace) => {
    setDetailLoading(true);
    try {
      const res = await agentApi.getTrace(trace.run_id);
      setSelectedTrace(res.data.trace);
    } catch (err) {
      console.error(err);
      // Show trace without steps if detail fetch fails
      setSelectedTrace(trace);
    } finally {
      setDetailLoading(false);
    }
  };

  const filteredTraces = traces.filter(t =>
    t.prompt?.toLowerCase().includes(search.toLowerCase()) ||
    t.model_used?.toLowerCase().includes(search.toLowerCase()) ||
    t.run_id?.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="w-8 h-8 rounded-full border-t-2 border-primary animate-spin" />
      </div>
    );
  }

  // Detail view
  if (selectedTrace) {
    return (
      <div className="max-w-5xl mx-auto pb-12">
        <button
          onClick={() => setSelectedTrace(null)}
          className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors mb-6 cursor-pointer"
        >
          <ArrowLeft size={16} />
          <span className="text-sm font-medium">Back to Traces</span>
        </button>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
        >
          {/* Trace Header */}
          <div className="glass-panel rounded-2xl p-6 mb-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                {selectedTrace.success ? (
                  <CheckCircle size={20} className="text-emerald-400" />
                ) : (
                  <XCircle size={20} className="text-red-400" />
                )}
                <h2 className="text-xl font-bold tracking-tight">Trace Detail</h2>
              </div>
              <span className="text-xs font-mono text-muted-foreground">
                {selectedTrace.run_id}
              </span>
            </div>

            {/* Prompt */}
            <div className="mb-4 p-3 bg-white/[0.02] rounded-lg border border-white/[0.05]">
              <span className="text-xs text-muted-foreground uppercase tracking-wider block mb-1">Prompt</span>
              <p className="text-sm text-foreground">{selectedTrace.prompt}</p>
            </div>

            {/* Metrics Row */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <div>
                <span className="text-xs text-muted-foreground block">Model</span>
                <span className="text-sm font-semibold uppercase">{selectedTrace.model_used}</span>
              </div>
              <div>
                <span className="text-xs text-muted-foreground block">Steps</span>
                <span className="text-sm font-semibold">{selectedTrace.total_steps}</span>
              </div>
              <div>
                <span className="text-xs text-muted-foreground block">Latency</span>
                <span className="text-sm font-semibold">{(selectedTrace.total_latency_ms / 1000).toFixed(1)}s</span>
              </div>
              <div>
                <span className="text-xs text-muted-foreground block">Tokens</span>
                <span className="text-sm font-semibold">{selectedTrace.total_tokens?.toLocaleString() ?? 0}</span>
              </div>
              <div>
                <span className="text-xs text-muted-foreground block">Cost</span>
                <span className="text-sm font-semibold">${selectedTrace.total_cost_usd?.toFixed(6) ?? '0.000000'}</span>
              </div>
            </div>

            {/* Tools Used */}
            {selectedTrace.tools_used && selectedTrace.tools_used.length > 0 && (
              <div className="mt-4 flex items-center gap-2 flex-wrap">
                <Wrench size={14} className="text-muted-foreground" />
                {selectedTrace.tools_used.map(tool => (
                  <span key={tool} className="text-xs px-2 py-0.5 rounded-full bg-white/5 border border-white/10 font-mono">
                    {tool}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Step Timeline */}
          <div className="glass-panel rounded-2xl p-6">
            <h3 className="text-lg font-semibold mb-4 tracking-tight">Execution Timeline</h3>
            {detailLoading ? (
              <div className="flex items-center justify-center h-32">
                <div className="w-6 h-6 rounded-full border-t-2 border-primary animate-spin" />
              </div>
            ) : selectedTrace.steps && selectedTrace.steps.length > 0 ? (
              <AgentTimeline steps={selectedTrace.steps as AgentEvent[]} />
            ) : (
              <div className="text-center text-muted-foreground text-sm py-8">
                No step data available for this trace.
              </div>
            )}
          </div>

          {/* Final Answer */}
          {selectedTrace.final_answer && (
            <div className="glass-panel rounded-2xl p-6 mt-6">
              <h3 className="text-lg font-semibold mb-3 tracking-tight">Final Answer</h3>
              <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">
                {selectedTrace.final_answer}
              </p>
            </div>
          )}
        </motion.div>
      </div>
    );
  }

  // List view
  return (
    <div className="max-w-5xl mx-auto pb-12">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight mb-1">Agent Traces</h1>
          <p className="text-muted-foreground">Inspect past agent executions with full step-by-step traces.</p>
        </div>
      </div>

      {/* Search */}
      <div className="mb-6">
        <div className="relative w-72">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search prompts, models..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full bg-input/50 border border-card-border rounded-lg pl-9 pr-4 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      {/* Trace List */}
      <div className="space-y-3">
        {filteredTraces.length === 0 ? (
          <div className="glass-panel rounded-2xl p-12 text-center text-muted-foreground">
            {traces.length === 0
              ? 'No agent traces yet. Run the agent to create your first trace.'
              : 'No traces matching your search.'}
          </div>
        ) : (
          filteredTraces.map((trace, idx) => (
            <motion.button
              key={trace.run_id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.03 }}
              onClick={() => handleSelectTrace(trace)}
              className="w-full text-left glass-panel rounded-xl p-5 hover:bg-white/[0.03] transition-colors cursor-pointer group border border-transparent hover:border-primary/20"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  {/* Status + Prompt */}
                  <div className="flex items-center gap-2 mb-2">
                    {trace.success ? (
                      <CheckCircle size={14} className="text-emerald-400 flex-shrink-0" />
                    ) : (
                      <XCircle size={14} className="text-red-400 flex-shrink-0" />
                    )}
                    <span className="text-sm font-medium text-foreground truncate">
                      {trace.prompt || 'No prompt'}
                    </span>
                  </div>

                  {/* Metrics Row */}
                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <span className="uppercase font-semibold tracking-wider">{trace.model_used}</span>
                    <span className="flex items-center gap-1">
                      <Hash size={10} /> {trace.total_steps} steps
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock size={10} /> {(trace.total_latency_ms / 1000).toFixed(1)}s
                    </span>
                    {trace.tools_used && trace.tools_used.length > 0 && (
                      <span className="flex items-center gap-1">
                        <Wrench size={10} /> {trace.tools_used.join(', ')}
                      </span>
                    )}
                    <span>{new Date(trace.timestamp).toLocaleString()}</span>
                  </div>
                </div>

                <ChevronRight size={16} className="text-muted-foreground group-hover:text-primary transition-colors flex-shrink-0 mt-1" />
              </div>
            </motion.button>
          ))
        )}
      </div>
    </div>
  );
};

export default Traces;
