/**
 * Component: AgentStepCard
 * Purpose: Displays a single step in the agent execution trace.
 * WHY: Each agent step (thinking, tool call, tool result, etc.) gets a visually distinct card
 * with an icon, type badge, content, and optional metrics. This is the atomic building block
 * for both the real-time streaming view and the post-run trace detail.
 */
import React from 'react';
import { motion } from 'framer-motion';
import { Brain, Search, Code, Database, FileText, CheckCircle, AlertCircle, Play } from 'lucide-react';
import type { AgentEvent } from '@/types';

const eventConfig: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  run_start: { icon: <Play size={14} />, color: 'text-blue-400 bg-blue-400/10 border-blue-400/20', label: 'Start' },
  thinking: { icon: <Brain size={14} />, color: 'text-purple-400 bg-purple-400/10 border-purple-400/20', label: 'Thinking' },
  tool_call: { icon: <Search size={14} />, color: 'text-amber-400 bg-amber-400/10 border-amber-400/20', label: 'Tool Call' },
  tool_result: { icon: <CheckCircle size={14} />, color: 'text-green-400 bg-green-400/10 border-green-400/20', label: 'Result' },
  final_answer: { icon: <CheckCircle size={14} />, color: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20', label: 'Answer' },
  error: { icon: <AlertCircle size={14} />, color: 'text-red-400 bg-red-400/10 border-red-400/20', label: 'Error' },
  run_end: { icon: <CheckCircle size={14} />, color: 'text-blue-400 bg-blue-400/10 border-blue-400/20', label: 'Complete' },
};

const toolIcons: Record<string, React.ReactNode> = {
  web_search: <Search size={14} />,
  code_execute: <Code size={14} />,
  db_query: <Database size={14} />,
  doc_analyze: <FileText size={14} />,
};

interface AgentStepCardProps {
  event: AgentEvent;
  index: number;
}

const AgentStepCard: React.FC<AgentStepCardProps> = ({ event, index }) => {
  const config = eventConfig[event.event_type] || eventConfig.thinking;

  // Don't render run_end events as cards (those are handled by AgentSummaryCard)
  if (event.event_type === 'run_end') return null;

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3 }}
      className={`p-4 rounded-xl border ${config.color} backdrop-blur-sm`}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {event.tool_name ? (toolIcons[event.tool_name] || config.icon) : config.icon}
          <span className="text-xs font-semibold uppercase tracking-wider">{config.label}</span>
          {event.tool_name && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-white/5 border border-white/10 font-mono">
              {event.tool_name}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {event.latency_ms != null && (
            <span>{Math.round(event.latency_ms)}ms</span>
          )}
          {event.tokens != null && event.tokens > 0 && (
            <span>{event.tokens} tok</span>
          )}
        </div>
      </div>

      {/* Tool input (for tool_call events) */}
      {event.tool_input && (
        <div className="mb-2 p-2 bg-black/20 rounded-lg text-xs font-mono text-muted-foreground truncate">
          {event.tool_input}
        </div>
      )}

      {/* Content */}
      <div className="text-sm leading-relaxed whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
        {event.content}
      </div>
    </motion.div>
  );
};

export default AgentStepCard;
