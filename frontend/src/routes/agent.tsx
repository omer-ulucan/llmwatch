/**
 * Component: Agent
 * Purpose: Main agent execution interface with tool configuration and real-time step timeline.
 * WHY: This is the primary UI for the ReAct agent feature. It combines a left config panel
 * (model selection + tool toggles + iteration slider) with a right panel showing the live
 * execution timeline streamed via SSE. The layout mirrors the Chat page for consistency.
 */
import React, { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Send, Bot, Zap, Loader2, RotateCcw, BrainCircuit } from 'lucide-react';
import AgentTimeline from '@/components/agent/AgentTimeline';
import AgentToolConfig from '@/components/agent/AgentToolConfig';
import AgentSummaryCard from '@/components/agent/AgentSummaryCard';
import { useAgentStream } from '@/hooks/useAgentStream';
import type { AgentRunRequest } from '@/types';

const Agent: React.FC = () => {
  const [prompt, setPrompt] = useState('');
  const [selectedModel, setSelectedModel] = useState<'qwen' | 'gemini'>('gemini');
  const [selectedTools, setSelectedTools] = useState<string[]>(['web_search', 'code_execute', 'db_query', 'doc_analyze']);
  const [maxIterations, setMaxIterations] = useState(10);

  const { steps, isRunning, error, summary, runAgent, reset } = useAgentStream();
  const timelineEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    timelineEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [steps]);

  const handleRun = async () => {
    if (!prompt.trim() || isRunning) return;

    const request: AgentRunRequest = {
      prompt: prompt.trim(),
      model: selectedModel,
      tools: selectedTools,
      max_iterations: maxIterations,
    };

    await runAgent(request);
  };

  const handleReset = () => {
    reset();
    setPrompt('');
  };

  return (
    <div className="flex bg-background h-[calc(100vh-8rem)] rounded-2xl overflow-hidden glass-card border border-card-border relative z-10">

      {/* Left Panel: Configuration */}
      <div className="w-80 border-r border-border bg-card/50 p-6 flex flex-col flex-shrink-0 overflow-y-auto">
        <h3 className="text-lg font-semibold mb-6 flex items-center gap-2">
          <BrainCircuit className="text-primary" />
          Agent Config
        </h3>

        {/* Model Selection */}
        <div className="space-y-2 mb-6">
          <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
            Model
          </h4>
          {(['qwen', 'gemini'] as const).map(m => (
            <button
              key={m}
              onClick={() => setSelectedModel(m)}
              className={`w-full text-left p-3 rounded-xl border transition-all duration-300 relative overflow-hidden group cursor-pointer ${
                selectedModel === m
                  ? 'bg-primary/10 border-primary glow-effect'
                  : 'bg-white/[0.02] border-card-border hover:bg-white/[0.05]'
              }`}
            >
              <div className="flex justify-between items-center">
                <span className="font-semibold capitalize text-foreground text-sm">
                  {m === 'qwen' ? 'Qwen3.5-35B' : 'Gemini 3 Flash'}
                </span>
                <div className={`w-2 h-2 rounded-full ${selectedModel === m ? 'bg-primary shadow-[0_0_8px_rgba(59,130,246,0.8)]' : 'bg-muted-foreground'}`} />
              </div>
              <span className="text-xs text-muted-foreground">
                {m === 'qwen' ? 'Self-hosted vLLM' : 'Google API'}
              </span>
            </button>
          ))}
        </div>

        {/* Tool Selection */}
        <div className="mb-6">
          <AgentToolConfig selectedTools={selectedTools} onChange={setSelectedTools} />
        </div>

        {/* Max Iterations */}
        <div className="mb-6">
          <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
            Max Iterations
          </h4>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={1}
              max={20}
              value={maxIterations}
              onChange={e => setMaxIterations(Number(e.target.value))}
              className="flex-1 accent-primary"
            />
            <span className="text-sm font-mono text-foreground w-6 text-right">{maxIterations}</span>
          </div>
        </div>

        {/* Session Stats */}
        <div className="mt-auto p-4 bg-white/[0.02] rounded-xl border border-white/[0.05]">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block mb-2">Run Stats</span>
          <div className="flex justify-between items-center text-sm mb-1">
            <span className="text-muted-foreground">Steps</span>
            <span>{steps.filter(s => s.event_type !== 'run_end').length}</span>
          </div>
          <div className="flex justify-between items-center text-sm mb-1">
            <span className="text-muted-foreground">Tools</span>
            <span>{selectedTools.length} enabled</span>
          </div>
          <div className="flex justify-between items-center text-sm">
            <span className="text-muted-foreground">Status</span>
            <span className={isRunning ? 'text-amber-400' : summary ? (summary.success ? 'text-emerald-400' : 'text-red-400') : 'text-muted-foreground'}>
              {isRunning ? 'Running...' : summary ? (summary.success ? 'Complete' : 'Failed') : 'Idle'}
            </span>
          </div>
        </div>
      </div>

      {/* Right Panel: Timeline + Input */}
      <div className="flex-1 flex flex-col relative w-full overflow-hidden">
        <div className="flex-1 overflow-y-auto overflow-x-hidden p-6 space-y-4">
          {steps.length === 0 && !isRunning ? (
            <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-4">
              <Zap size={48} className="text-primary/20" />
              <p className="text-center max-w-md">
                Configure tools and enter a prompt to start the agent.
                The agent will reason step-by-step, using tools as needed.
              </p>
            </div>
          ) : (
            <>
              {/* User prompt display */}
              {prompt && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex gap-4 justify-end"
                >
                  <div className="max-w-[80%]">
                    <div className="p-4 rounded-2xl bg-gradient-to-br from-primary to-primary-hover text-white rounded-tr-sm">
                      <p className="whitespace-pre-wrap leading-relaxed">{prompt}</p>
                    </div>
                  </div>
                </motion.div>
              )}

              {/* Agent Timeline */}
              <div className="flex gap-4 justify-start">
                <div className="w-8 h-8 rounded-full bg-primary/20 text-primary flex items-center justify-center flex-shrink-0 mt-1">
                  <Bot size={16} />
                </div>
                <div className="flex-1 min-w-0 space-y-4">
                  <AgentTimeline steps={steps} />

                  {/* Summary Card */}
                  {summary && <AgentSummaryCard summary={summary} />}

                  {/* Error Display */}
                  {error && !isRunning && (
                    <div className="p-4 rounded-xl bg-red-500/5 border border-red-500/20 text-red-400 text-sm">
                      {error}
                    </div>
                  )}
                </div>
              </div>

              {/* Loading indicator */}
              {isRunning && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-4">
                  <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center">
                    <Bot size={16} className="text-muted-foreground" />
                  </div>
                  <div className="glass-panel p-4 rounded-2xl rounded-tl-sm flex items-center gap-2 text-muted-foreground">
                    <Loader2 className="animate-spin" size={16} />
                    <span className="text-sm">Agent is reasoning...</span>
                  </div>
                </motion.div>
              )}
            </>
          )}
          <div ref={timelineEndRef} />
        </div>

        {/* Input Bar */}
        <div className="p-4 bg-background/80 backdrop-blur-md border-t border-border">
          <div className="max-w-4xl mx-auto relative flex items-center gap-2">
            {(summary || error) && !isRunning && (
              <button
                onClick={handleReset}
                className="p-2.5 bg-white/[0.03] hover:bg-white/[0.08] border border-card-border rounded-xl transition-colors cursor-pointer"
                title="Reset"
              >
                <RotateCcw size={16} className="text-muted-foreground" />
              </button>
            )}
            <div className="flex-1 relative">
              <textarea
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleRun();
                  }
                }}
                placeholder="Ask the agent anything... (e.g. 'Search for the latest AI news and summarize it')"
                className="w-full bg-input/50 border border-card-border rounded-xl pl-4 pr-14 py-4 text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 resize-none overflow-hidden h-[56px]"
                rows={1}
                disabled={isRunning}
              />
              <button
                onClick={handleRun}
                disabled={isRunning || !prompt.trim() || selectedTools.length === 0}
                className="absolute right-3 top-1/2 -translate-y-1/2 p-2 bg-primary text-white rounded-lg hover:bg-primary-hover disabled:opacity-50 transition-colors shadow-lg cursor-pointer"
              >
                {isRunning ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Agent;
