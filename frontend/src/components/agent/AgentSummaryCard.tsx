/**
 * Component: AgentSummaryCard
 * Purpose: Post-run summary showing total metrics for an agent execution.
 * WHY: After the agent completes, this card provides at-a-glance metrics — total steps,
 * latency, tokens, cost, tools used, and success status. It's the "receipt" for the agent run.
 */
import React from 'react';
import { motion } from 'framer-motion';
import { CheckCircle, XCircle, Clock, Hash, Coins, Wrench } from 'lucide-react';
import type { AgentRunSummary } from '@/types';

interface AgentSummaryCardProps {
  summary: AgentRunSummary;
}

const AgentSummaryCard: React.FC<AgentSummaryCardProps> = ({ summary }) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={`p-5 rounded-xl border backdrop-blur-sm ${
        summary.success
          ? 'bg-emerald-500/5 border-emerald-500/20'
          : 'bg-red-500/5 border-red-500/20'
      }`}
    >
      {/* Status Header */}
      <div className="flex items-center gap-2 mb-4">
        {summary.success ? (
          <CheckCircle size={18} className="text-emerald-400" />
        ) : (
          <XCircle size={18} className="text-red-400" />
        )}
        <span className="font-semibold text-sm">
          {summary.success ? 'Agent Run Complete' : 'Agent Run Failed'}
        </span>
        <span className="text-xs text-muted-foreground ml-auto font-mono">
          {summary.model_used}
        </span>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 gap-3">
        <div className="flex items-center gap-2 text-sm">
          <Hash size={14} className="text-muted-foreground" />
          <span className="text-muted-foreground">Steps:</span>
          <span className="font-medium">{summary.total_steps}</span>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <Clock size={14} className="text-muted-foreground" />
          <span className="text-muted-foreground">Latency:</span>
          <span className="font-medium">{(summary.total_latency_ms / 1000).toFixed(1)}s</span>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground text-xs">TOK</span>
          <span className="text-muted-foreground">Tokens:</span>
          <span className="font-medium">{summary.total_tokens.toLocaleString()}</span>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <Coins size={14} className="text-muted-foreground" />
          <span className="text-muted-foreground">Cost:</span>
          <span className="font-medium">${summary.total_cost_usd.toFixed(6)}</span>
        </div>
      </div>

      {/* Tools Used */}
      {summary.tools_used.length > 0 && (
        <div className="mt-3 flex items-center gap-2 flex-wrap">
          <Wrench size={14} className="text-muted-foreground" />
          {summary.tools_used.map(tool => (
            <span key={tool} className="text-xs px-2 py-0.5 rounded-full bg-white/5 border border-white/10 font-mono">
              {tool}
            </span>
          ))}
        </div>
      )}
    </motion.div>
  );
};

export default AgentSummaryCard;
